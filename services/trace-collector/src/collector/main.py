"""
Trace Collector Service - Receives and stores trace events.

This service provides:
- REST API for receiving trace events
- Storage in SQLite + JSONL files
- Analysis endpoints for querying traces
"""

import json
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

log = structlog.get_logger()

# Configuration
DATA_DIR = os.getenv("TRACE_DATA_DIR", "data/traces")
DB_PATH = os.getenv("TRACE_DB_PATH", f"{DATA_DIR}/traces.db")


class TraceEvent(BaseModel):
    """A single trace event."""
    trace_id: str
    turn_id: str
    span_id: str
    service: str
    event: str
    ts_ms: int
    mono_ms: float
    parent_span_id: Optional[str] = None
    payload: dict[str, Any] = {}


class TraceEventsRequest(BaseModel):
    """Request containing multiple trace events."""
    events: list[TraceEvent]


# Database setup
def init_db():
    """Initialize SQLite database."""
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id TEXT NOT NULL,
            turn_id TEXT,
            span_id TEXT,
            service TEXT,
            event TEXT,
            ts_ms INTEGER,
            mono_ms REAL,
            parent_span_id TEXT,
            payload TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trace_id ON traces(trace_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_turn_id ON traces(turn_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_event ON traces(event)")

    conn.commit()
    conn.close()
    log.info("database_initialized", db_path=DB_PATH)


def get_db():
    """Get database connection."""
    return sqlite3.connect(DB_PATH)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events."""
    log.info("trace_collector_starting", data_dir=DATA_DIR)
    init_db()
    yield
    log.info("trace_collector_stopping")


app = FastAPI(
    title="AI Kiosk Trace Collector",
    description="Collects and stores trace events for analysis",
    version="0.1.0",
    lifespan=lifespan,
)

# Enable CORS for Trace Viewer
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "trace-collector",
        "version": "0.1.0",
    }


@app.post("/traces")
async def receive_traces(events: list[TraceEvent]):
    """Receive and store trace events."""
    if not events:
        return {"received": 0}

    conn = get_db()
    cursor = conn.cursor()

    # Group events by trace_id for JSONL storage
    events_by_trace: dict[str, list[TraceEvent]] = {}

    for event in events:
        # Store in SQLite
        cursor.execute("""
            INSERT INTO traces (trace_id, turn_id, span_id, service, event, ts_ms, mono_ms, parent_span_id, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event.trace_id,
            event.turn_id,
            event.span_id,
            event.service,
            event.event,
            event.ts_ms,
            event.mono_ms,
            event.parent_span_id,
            json.dumps(event.payload),
        ))

        # Group for JSONL
        events_by_trace.setdefault(event.trace_id, []).append(event)

    conn.commit()
    conn.close()

    # Write to JSONL files
    for trace_id, trace_events in events_by_trace.items():
        trace_dir = Path(DATA_DIR) / "sessions" / trace_id
        trace_dir.mkdir(parents=True, exist_ok=True)

        events_file = trace_dir / "events.jsonl"
        with open(events_file, "a") as f:
            for event in trace_events:
                f.write(json.dumps(event.model_dump()) + "\n")

    log.info("traces_received", count=len(events))
    return {"received": len(events)}


@app.get("/traces/{trace_id}")
async def get_trace(trace_id: str):
    """Get all events for a trace."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT trace_id, turn_id, span_id, service, event, ts_ms, mono_ms, parent_span_id, payload
        FROM traces
        WHERE trace_id = ?
        ORDER BY mono_ms
    """, (trace_id,))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        raise HTTPException(status_code=404, detail=f"Trace not found: {trace_id}")

    events = []
    for row in rows:
        events.append({
            "trace_id": row[0],
            "turn_id": row[1],
            "span_id": row[2],
            "service": row[3],
            "event": row[4],
            "ts_ms": row[5],
            "mono_ms": row[6],
            "parent_span_id": row[7],
            "payload": json.loads(row[8]) if row[8] else {},
        })

    return events


@app.get("/traces")
async def list_traces(
    limit: int = 50,
    turn_id: Optional[str] = None,
    service: Optional[str] = None,
):
    """List traces with optional filters."""
    conn = get_db()
    cursor = conn.cursor()

    query = "SELECT DISTINCT trace_id FROM traces WHERE 1=1"
    params = []

    if turn_id:
        query += " AND turn_id = ?"
        params.append(turn_id)

    if service:
        query += " AND service = ?"
        params.append(service)

    query += f" ORDER BY ts_ms DESC LIMIT {limit}"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return {"traces": [row[0] for row in rows]}


@app.get("/analysis/{trace_id}")
async def analyze_trace(trace_id: str):
    """Analyze a trace and return metrics."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT trace_id, turn_id, span_id, service, event, ts_ms, mono_ms, parent_span_id, payload
        FROM traces
        WHERE trace_id = ?
        ORDER BY mono_ms
    """, (trace_id,))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        raise HTTPException(status_code=404, detail=f"Trace not found: {trace_id}")

    events = []
    for row in rows:
        events.append({
            "trace_id": row[0],
            "turn_id": row[1],
            "span_id": row[2],
            "service": row[3],
            "event": row[4],
            "ts_ms": row[5],
            "mono_ms": row[6],
            "parent_span_id": row[7],
            "payload": json.loads(row[8]) if row[8] else {},
        })

    # Calculate latencies
    latencies = {}
    turns = {}

    for event in events:
        turn_id = event["turn_id"]
        if turn_id:
            turns.setdefault(turn_id, []).append(event)

    for turn_id, turn_events in turns.items():
        # Turn latency
        turn_start = next((e for e in turn_events if "turn_start" in e["event"]), None)
        turn_end = next((e for e in turn_events if "turn_end" in e["event"]), None)
        if turn_start and turn_end:
            latencies[f"turn_{turn_id}_total"] = turn_end["mono_ms"] - turn_start["mono_ms"]

        # Classify latency
        classify_start = next((e for e in turn_events if "classify_start" in e["event"]), None)
        classify_end = next((e for e in turn_events if "classify_end" in e["event"]), None)
        if classify_start and classify_end:
            latencies[f"turn_{turn_id}_classify"] = classify_end["mono_ms"] - classify_start["mono_ms"]

    # Build timeline
    start_ms = events[0]["mono_ms"] if events else 0
    timeline = []
    for event in events:
        timeline.append({
            "offset_ms": round(event["mono_ms"] - start_ms, 2),
            "service": event["service"],
            "event": event["event"],
            "turn_id": event["turn_id"],
            "span_id": event["span_id"],
        })

    return {
        "trace_id": trace_id,
        "event_count": len(events),
        "turn_count": len(turns),
        "latencies": latencies,
        "timeline": timeline,
    }


def run_server():
    """Run the collector server."""
    import uvicorn

    host = os.getenv("TRACE_COLLECTOR_HOST", "0.0.0.0")
    port = int(os.getenv("TRACE_COLLECTOR_PORT", "9002"))

    log.info("starting_trace_collector", host=host, port=port)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
