"""
Tracing module for AI Kiosk services.

Provides a unified trace event schema and emitter for observability.
All services emit events to a central TraceCollector for latency analysis.
"""

import time
import json
import os
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any
import httpx


class Events(str, Enum):
    """Standard trace event names across all services."""

    # VAD/ASR events (Speech service)
    VAD_START = "vad.start"
    VAD_END = "vad.end"
    ASR_START = "asr.start"
    ASR_PARTIAL = "asr.partial"
    ASR_FINAL = "asr.final"

    # LLM events (Orchestrator)
    INTENT_DETECTED = "intent.detected"
    LLM_FIRST_TOKEN = "llm.first_token"
    LLM_COMPLETE = "llm.complete"

    # Tool events (MCP/Orchestrator)
    TOOL_CALL_START = "tool.call.start"
    TOOL_CALL_END = "tool.call.end"
    TOOL_CALL_ERROR = "tool.call.error"

    # TTS events (Speech service)
    TTS_START = "tts.start"
    TTS_FIRST_CHUNK = "tts.first_chunk"
    TTS_END = "tts.end"

    # Orchestrator turn events
    TURN_START = "orch.turn.start"
    TURN_END = "orch.turn.end"
    PLAN_CREATED = "plan.created"

    # UI/Playback events
    PLAYBACK_START = "playback.start"
    PLAYBACK_END = "playback.end"
    BARGE_IN = "barge_in.detected"
    TTS_STOP_REQUESTED = "tts.stop.requested"
    TTS_STOP_ACK = "tts.stop.ack"


@dataclass
class TraceEvent:
    """
    Unified trace event schema.

    Attributes:
        trace_id: Session-level ID (persists across entire conversation)
        turn_id: Turn-level ID (one per user utterance)
        span_id: Unique ID for this work unit
        service: Emitting service name (ui, speech, orchestrator, mcp)
        event: Event name (from Events enum or custom)
        ts_ms: Wall-clock timestamp (epoch milliseconds)
        mono_ms: Monotonic timestamp (for accurate duration calculation)
        parent_span_id: Parent span for hierarchical tracing
        level: Log level (DEBUG, INFO, WARN, ERROR)
        attrs: Additional event-specific attributes
    """

    trace_id: str
    turn_id: str
    span_id: str
    service: str
    event: str
    ts_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    mono_ms: int = field(default_factory=lambda: int(time.monotonic() * 1000))
    parent_span_id: str | None = None
    level: str = "INFO"
    attrs: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


class TraceEmitter:
    """
    Emits trace events to a TraceCollector service.

    The emitter is non-blocking - failures to send events are logged but don't
    interrupt the main flow.
    """

    def __init__(
        self,
        service: str,
        collector_url: str | None = None,
        output_dir: str | None = None,
        enabled: bool = True,
    ):
        """
        Initialize the trace emitter.

        Args:
            service: Name of the emitting service
            collector_url: URL of the TraceCollector service
            output_dir: Directory to write trace files (fallback/dev mode)
            enabled: Whether tracing is enabled
        """
        self.service = service
        self.collector_url = collector_url
        self.output_dir = output_dir
        self.enabled = enabled
        self._client: httpx.AsyncClient | None = None
        self._mono_start = int(time.monotonic() * 1000)

        if collector_url and enabled:
            self._client = httpx.AsyncClient(timeout=1.0)

    async def emit(
        self,
        event: str | Events,
        trace_id: str,
        turn_id: str,
        span_id: str,
        parent_span_id: str | None = None,
        level: str = "INFO",
        **attrs: Any,
    ) -> TraceEvent | None:
        """
        Emit a trace event.

        Args:
            event: Event name (from Events enum or custom string)
            trace_id: Session-level trace ID
            turn_id: Turn-level ID
            span_id: Unique span ID for this work unit
            parent_span_id: Parent span ID (optional)
            level: Log level
            **attrs: Additional event attributes

        Returns:
            The emitted TraceEvent, or None if tracing is disabled
        """
        if not self.enabled:
            return None

        # Convert enum to string if needed
        event_name = event.value if isinstance(event, Events) else event

        trace_event = TraceEvent(
            trace_id=trace_id,
            turn_id=turn_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            service=self.service,
            event=event_name,
            level=level,
            attrs=attrs,
        )

        # Send to collector (non-blocking)
        if self._client and self.collector_url:
            try:
                await self._client.post(
                    f"{self.collector_url}/trace/event",
                    json=trace_event.to_dict(),
                )
            except Exception:
                # Non-blocking - don't interrupt main flow
                pass

        # Optionally write to file (for development/debugging)
        if self.output_dir:
            try:
                import aiofiles
                from pathlib import Path

                output_path = Path(self.output_dir)
                output_path.mkdir(parents=True, exist_ok=True)

                filename = output_path / f"{trace_id}.jsonl"
                async with aiofiles.open(filename, "a") as f:
                    await f.write(trace_event.to_json() + "\n")
            except Exception:
                pass

        return trace_event

    def emit_sync(
        self,
        event: str | Events,
        trace_id: str,
        turn_id: str,
        span_id: str,
        parent_span_id: str | None = None,
        level: str = "INFO",
        **attrs: Any,
    ) -> TraceEvent | None:
        """
        Synchronous version of emit (for non-async contexts).

        Uses synchronous HTTP client instead of async.
        """
        if not self.enabled:
            return None

        event_name = event.value if isinstance(event, Events) else event

        trace_event = TraceEvent(
            trace_id=trace_id,
            turn_id=turn_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            service=self.service,
            event=event_name,
            level=level,
            attrs=attrs,
        )

        if self.collector_url:
            try:
                httpx.post(
                    f"{self.collector_url}/trace/event",
                    json=trace_event.to_dict(),
                    timeout=1.0,
                )
            except Exception:
                pass

        return trace_event

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()


# Global emitter instance (configured per service)
_emitter: TraceEmitter | None = None


def configure_emitter(
    service: str,
    collector_url: str | None = None,
    output_dir: str | None = None,
    enabled: bool = True,
) -> TraceEmitter:
    """
    Configure and return the global trace emitter.

    Args:
        service: Name of the service
        collector_url: URL of the TraceCollector
        output_dir: Directory for trace file output
        enabled: Whether tracing is enabled

    Returns:
        Configured TraceEmitter instance
    """
    global _emitter

    # Use environment variables as defaults
    if collector_url is None:
        collector_url = os.getenv("TRACE_COLLECTOR_URL")

    if output_dir is None:
        output_dir = os.getenv("TRACE_OUTPUT_DIR")

    env_enabled = os.getenv("TRACING_ENABLED", "true").lower() == "true"
    enabled = enabled and env_enabled

    _emitter = TraceEmitter(
        service=service,
        collector_url=collector_url,
        output_dir=output_dir,
        enabled=enabled,
    )

    return _emitter


def get_emitter() -> TraceEmitter | None:
    """Get the global trace emitter instance."""
    return _emitter


def generate_span_id() -> str:
    """Generate a unique span ID."""
    import uuid

    return f"span-{uuid.uuid4().hex[:12]}"
