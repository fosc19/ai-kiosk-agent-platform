"""
Trace Collector Service.

Receives trace events from all AI Kiosk services and stores them for analysis.
Provides endpoints for querying traces and calculating latency metrics.
"""

import json
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

# Configuration
DB_PATH = os.getenv("TRACE_DB_PATH", "data/traces.db")
RETENTION_HOURS = int(os.getenv("TRACE_RETENTION_HOURS", "24"))


class TraceEventIn(BaseModel):
    """Incoming trace event schema."""

    trace_id: str
    turn_id: str
    span_id: str
    parent_span_id: str | None = None
    service: str
    event: str
    ts_ms: int
    mono_ms: int
    level: str = "INFO"
    attrs: dict[str, Any] = {}


class MetricsResponse(BaseModel):
    """Response for metrics endpoint."""

    window: str
    sample_count: int
    metrics: dict[str, dict[str, float]]


def get_db_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database schema."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id TEXT NOT NULL,
            turn_id TEXT NOT NULL,
            span_id TEXT NOT NULL,
            parent_span_id TEXT,
            service TEXT NOT NULL,
            event TEXT NOT NULL,
            ts_ms INTEGER NOT NULL,
            mono_ms INTEGER NOT NULL,
            level TEXT DEFAULT 'INFO',
            attrs TEXT DEFAULT '{}',
            created_at INTEGER DEFAULT (strftime('%s', 'now'))
        )
    """)

    # Create indexes for efficient queries
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_id ON events(trace_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_turn_id ON events(turn_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_event ON events(event)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts_ms ON events(ts_ms)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trace_turn ON events(trace_id, turn_id)"
    )
    conn.commit()
    conn.close()


def cleanup_old_events():
    """Remove events older than retention period."""
    cutoff_ms = int((time.time() - RETENTION_HOURS * 3600) * 1000)
    conn = get_db_connection()
    conn.execute("DELETE FROM events WHERE ts_ms < ?", (cutoff_ms,))
    conn.commit()
    conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    init_db()
    yield
    # Cleanup on shutdown
    cleanup_old_events()


app = FastAPI(
    title="Trace Collector",
    description="Collects and analyzes trace events from AI Kiosk services",
    version="1.0.0",
    lifespan=lifespan,
)


@app.post("/trace/event")
async def receive_event(event: TraceEventIn) -> dict[str, str]:
    """
    Receive and store a trace event.

    This endpoint is called by all services to report trace events.
    It's designed to be non-blocking and fast.
    """
    conn = get_db_connection()
    try:
        conn.execute(
            """
            INSERT INTO events
            (trace_id, turn_id, span_id, parent_span_id, service, event, ts_ms, mono_ms, level, attrs)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.trace_id,
                event.turn_id,
                event.span_id,
                event.parent_span_id,
                event.service,
                event.event,
                event.ts_ms,
                event.mono_ms,
                event.level,
                json.dumps(event.attrs),
            ),
        )
        conn.commit()
        return {"status": "ok"}
    finally:
        conn.close()


@app.post("/trace/events")
async def receive_events(events: list[TraceEventIn]) -> dict[str, Any]:
    """Receive and store multiple trace events in batch."""
    conn = get_db_connection()
    try:
        for event in events:
            conn.execute(
                """
                INSERT INTO events
                (trace_id, turn_id, span_id, parent_span_id, service, event, ts_ms, mono_ms, level, attrs)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.trace_id,
                    event.turn_id,
                    event.span_id,
                    event.parent_span_id,
                    event.service,
                    event.event,
                    event.ts_ms,
                    event.mono_ms,
                    event.level,
                    json.dumps(event.attrs),
                ),
            )
        conn.commit()
        return {"status": "ok", "count": len(events)}
    finally:
        conn.close()


@app.get("/trace/turn/{trace_id}/{turn_id}")
async def get_turn_events(trace_id: str, turn_id: str) -> dict[str, Any]:
    """
    Get all events for a specific turn.

    Returns events ordered by timestamp for timeline analysis.
    """
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            """
            SELECT trace_id, turn_id, span_id, parent_span_id, service, event,
                   ts_ms, mono_ms, level, attrs
            FROM events
            WHERE trace_id = ? AND turn_id = ?
            ORDER BY ts_ms ASC
            """,
            (trace_id, turn_id),
        )
        events = []
        for row in cursor.fetchall():
            event = dict(row)
            event["attrs"] = json.loads(event["attrs"])
            events.append(event)
        return {"events": events, "count": len(events)}
    finally:
        conn.close()


@app.get("/trace/session/{trace_id}")
async def get_session_events(
    trace_id: str,
    limit: int = Query(default=1000, le=10000),
) -> dict[str, Any]:
    """
    Get all events for a session (trace_id).

    Returns events ordered by timestamp.
    """
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            """
            SELECT trace_id, turn_id, span_id, parent_span_id, service, event,
                   ts_ms, mono_ms, level, attrs
            FROM events
            WHERE trace_id = ?
            ORDER BY ts_ms ASC
            LIMIT ?
            """,
            (trace_id, limit),
        )
        events = []
        for row in cursor.fetchall():
            event = dict(row)
            event["attrs"] = json.loads(event["attrs"])
            events.append(event)
        return {"events": events, "count": len(events)}
    finally:
        conn.close()


@app.get("/metrics/turn/{trace_id}/{turn_id}")
async def get_turn_metrics(trace_id: str, turn_id: str) -> dict[str, Any]:
    """
    Calculate latency metrics for a specific turn.

    Returns timing breakdowns between key events.
    """
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            """
            SELECT event, mono_ms, ts_ms, attrs
            FROM events
            WHERE trace_id = ? AND turn_id = ?
            ORDER BY ts_ms ASC
            """,
            (trace_id, turn_id),
        )
        events = {row["event"]: row for row in cursor.fetchall()}

        metrics = {}

        # ASR latency: vad.end -> asr.final
        if "vad.end" in events and "asr.final" in events:
            metrics["asr_latency_ms"] = (
                events["asr.final"]["mono_ms"] - events["vad.end"]["mono_ms"]
            )

        # LLM first token: asr.final -> llm.first_token
        if "asr.final" in events and "llm.first_token" in events:
            metrics["llm_first_token_ms"] = (
                events["llm.first_token"]["mono_ms"] - events["asr.final"]["mono_ms"]
            )

        # LLM complete: asr.final -> llm.complete
        if "asr.final" in events and "llm.complete" in events:
            metrics["llm_complete_ms"] = (
                events["llm.complete"]["mono_ms"] - events["asr.final"]["mono_ms"]
            )

        # TTS first chunk: llm.first_token -> tts.first_chunk
        if "llm.first_token" in events and "tts.first_chunk" in events:
            metrics["tts_first_chunk_ms"] = (
                events["tts.first_chunk"]["mono_ms"]
                - events["llm.first_token"]["mono_ms"]
            )

        # End-to-end: vad.end -> tts.first_chunk (time to first audio)
        if "vad.end" in events and "tts.first_chunk" in events:
            metrics["end_to_end_first_audio_ms"] = (
                events["tts.first_chunk"]["mono_ms"] - events["vad.end"]["mono_ms"]
            )

        # Turn duration: orch.turn.start -> orch.turn.end
        if "orch.turn.start" in events and "orch.turn.end" in events:
            metrics["turn_duration_ms"] = (
                events["orch.turn.end"]["mono_ms"]
                - events["orch.turn.start"]["mono_ms"]
            )

        # Tool call duration (if any)
        if "tool.call.start" in events and "tool.call.end" in events:
            metrics["tool_call_ms"] = (
                events["tool.call.end"]["mono_ms"]
                - events["tool.call.start"]["mono_ms"]
            )

        return {
            "trace_id": trace_id,
            "turn_id": turn_id,
            "metrics": metrics,
            "event_count": len(events),
        }
    finally:
        conn.close()


@app.get("/metrics/summary")
async def get_metrics_summary(
    window: str = Query(default="5m", regex="^[0-9]+[mh]$"),
) -> MetricsResponse:
    """
    Get aggregated metrics for a time window.

    Window format: "5m" (minutes) or "1h" (hours)
    Returns p50, p90, p95, avg for each metric.
    """
    # Parse window
    if window.endswith("m"):
        minutes = int(window[:-1])
    elif window.endswith("h"):
        minutes = int(window[:-1]) * 60
    else:
        raise HTTPException(status_code=400, detail="Invalid window format")

    cutoff_ms = int((time.time() - minutes * 60) * 1000)

    conn = get_db_connection()
    try:
        # Get all turns in the window
        cursor = conn.execute(
            """
            SELECT DISTINCT trace_id, turn_id
            FROM events
            WHERE ts_ms >= ?
            """,
            (cutoff_ms,),
        )
        turns = cursor.fetchall()

        # Calculate metrics for each turn
        all_metrics: dict[str, list[float]] = {}

        for turn in turns:
            cursor = conn.execute(
                """
                SELECT event, mono_ms
                FROM events
                WHERE trace_id = ? AND turn_id = ?
                """,
                (turn["trace_id"], turn["turn_id"]),
            )
            events = {row["event"]: row["mono_ms"] for row in cursor.fetchall()}

            # Calculate individual metrics
            if "vad.end" in events and "asr.final" in events:
                val = events["asr.final"] - events["vad.end"]
                all_metrics.setdefault("asr_latency_ms", []).append(val)

            if "asr.final" in events and "llm.first_token" in events:
                val = events["llm.first_token"] - events["asr.final"]
                all_metrics.setdefault("llm_first_token_ms", []).append(val)

            if "vad.end" in events and "tts.first_chunk" in events:
                val = events["tts.first_chunk"] - events["vad.end"]
                all_metrics.setdefault("end_to_end_first_audio_ms", []).append(val)

            if "orch.turn.start" in events and "orch.turn.end" in events:
                val = events["orch.turn.end"] - events["orch.turn.start"]
                all_metrics.setdefault("turn_duration_ms", []).append(val)

        # Calculate percentiles
        def percentile(data: list[float], p: float) -> float:
            if not data:
                return 0.0
            sorted_data = sorted(data)
            k = (len(sorted_data) - 1) * p / 100
            f = int(k)
            c = f + 1 if f + 1 < len(sorted_data) else f
            return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])

        summary: dict[str, dict[str, float]] = {}
        for metric_name, values in all_metrics.items():
            if values:
                summary[metric_name] = {
                    "p50": round(percentile(values, 50), 2),
                    "p90": round(percentile(values, 90), 2),
                    "p95": round(percentile(values, 95), 2),
                    "avg": round(sum(values) / len(values), 2),
                    "min": round(min(values), 2),
                    "max": round(max(values), 2),
                    "count": len(values),
                }

        return MetricsResponse(
            window=window,
            sample_count=len(turns),
            metrics=summary,
        )
    finally:
        conn.close()


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    # Verify database connection
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1")
        conn.close()
        return {"status": "healthy"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {e}")


@app.delete("/trace/cleanup")
async def cleanup_traces(
    older_than_hours: int = Query(default=24, ge=1),
) -> dict[str, Any]:
    """
    Manually trigger cleanup of old traces.

    Removes events older than specified hours.
    """
    cutoff_ms = int((time.time() - older_than_hours * 3600) * 1000)
    conn = get_db_connection()
    try:
        cursor = conn.execute("DELETE FROM events WHERE ts_ms < ?", (cutoff_ms,))
        deleted = cursor.rowcount
        conn.commit()
        return {"status": "ok", "deleted_count": deleted}
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "9010"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)
