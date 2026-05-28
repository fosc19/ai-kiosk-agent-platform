"""
Trace emitter for services to emit trace events.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .models import TraceEvent, Events


logger = logging.getLogger(__name__)


@dataclass
class SpanContext:
    """Context for a span, used for hierarchical tracing."""
    span_id: str
    parent_span_id: Optional[str]
    start_mono_ms: float
    event_name: str


class TraceEmitter:
    """
    Emits trace events from a service.

    Can be configured to:
    - Send events to a collector service (HTTP)
    - Write events to local files (for development)
    - Buffer events in memory (for testing)

    Usage:
        emitter = TraceEmitter(service="orchestrator")

        # Simple event
        emitter.emit("turn_start", turn_id="t1", payload={"text": "Hola"})

        # Span with timing
        with emitter.span("llm_call", turn_id="t1") as span:
            result = await call_llm()
        # Automatically emits start/end events with duration
    """

    def __init__(
        self,
        service: str,
        collector_url: Optional[str] = None,
        output_dir: Optional[str] = None,
        enabled: bool = True,
        buffer_events: bool = False,
    ):
        """
        Initialize the trace emitter.

        Args:
            service: Name of the service emitting traces
            collector_url: URL of the trace collector (optional)
            output_dir: Directory to write trace files (optional)
            enabled: Whether tracing is enabled
            buffer_events: Whether to buffer events in memory (for testing)
        """
        self.service = service
        self.collector_url = collector_url or os.getenv("TRACE_COLLECTOR_URL")
        self.output_dir = output_dir or os.getenv("TRACE_OUTPUT_DIR")
        self.enabled = enabled and os.getenv("TRACING_ENABLED", "true").lower() == "true"
        self.buffer_events = buffer_events

        # Current trace context
        self._trace_id: Optional[str] = None
        self._current_spans: dict[str, SpanContext] = {}

        # Service start time for monotonic timestamps
        self._start_mono = time.monotonic()

        # Event buffer for testing
        self._event_buffer: list[TraceEvent] = []

        # Async queue for background sending
        self._event_queue: asyncio.Queue[TraceEvent] = asyncio.Queue()
        self._sender_task: Optional[asyncio.Task] = None

        if self.output_dir:
            Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    def set_trace_id(self, trace_id: str) -> None:
        """Set the current trace ID (typically session ID)."""
        self._trace_id = trace_id

    def get_trace_id(self) -> str:
        """Get current trace ID, creating one if needed."""
        if not self._trace_id:
            self._trace_id = str(uuid.uuid4())
        return self._trace_id

    def _get_mono_ms(self) -> float:
        """Get monotonic milliseconds since service start."""
        return (time.monotonic() - self._start_mono) * 1000

    def emit(
        self,
        event: str,
        turn_id: Optional[str] = None,
        span_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> TraceEvent:
        """
        Emit a trace event.

        Args:
            event: Event name (e.g., "turn_start")
            turn_id: Turn ID (optional)
            span_id: Span ID (optional, auto-generated if not provided)
            parent_span_id: Parent span ID for hierarchical tracing
            payload: Additional event data
            trace_id: Override trace ID (uses current if not provided)

        Returns:
            The emitted TraceEvent
        """
        if not self.enabled:
            return TraceEvent.create(self.service, event)

        trace_event = TraceEvent(
            trace_id=trace_id or self.get_trace_id(),
            turn_id=turn_id or "",
            span_id=span_id or str(uuid.uuid4()),
            parent_span_id=parent_span_id,
            service=self.service,
            event=event,
            mono_ms=self._get_mono_ms(),
            payload=payload or {},
        )

        self._handle_event(trace_event)
        return trace_event

    def _handle_event(self, event: TraceEvent) -> None:
        """Handle an emitted event (buffer, write, or send)."""
        if self.buffer_events:
            self._event_buffer.append(event)

        if self.output_dir:
            self._write_to_file(event)

        if self.collector_url:
            try:
                self._event_queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Trace event queue full, dropping event")

        # Always log in debug mode
        logger.debug(f"TRACE: {event.event} | turn={event.turn_id} | {event.payload}")

    def _write_to_file(self, event: TraceEvent) -> None:
        """Write event to local file."""
        if not self.output_dir:
            return

        # Organize by trace_id
        trace_dir = Path(self.output_dir) / event.trace_id
        trace_dir.mkdir(parents=True, exist_ok=True)

        # Append to events.jsonl
        events_file = trace_dir / "events.jsonl"
        with open(events_file, "a") as f:
            f.write(json.dumps(event.to_dict()) + "\n")

    @contextmanager
    def span(
        self,
        name: str,
        turn_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        start_payload: Optional[dict[str, Any]] = None,
    ):
        """
        Context manager for timing a span.

        Automatically emits start and end events with duration.

        Usage:
            with emitter.span("llm_call", turn_id="t1") as span_id:
                result = await call_llm()
            # Emits: orch.llm_call_start, orch.llm_call_end with duration_ms

        Args:
            name: Base name for the span (e.g., "llm_call")
            turn_id: Turn ID
            parent_span_id: Parent span for nesting
            start_payload: Additional data for start event

        Yields:
            span_id: The span ID for this operation
        """
        span_id = str(uuid.uuid4())
        start_event = f"{name}_start" if not name.endswith("_start") else name
        end_event = name.replace("_start", "_end") if name.endswith("_start") else f"{name}_end"

        # Track span context
        ctx = SpanContext(
            span_id=span_id,
            parent_span_id=parent_span_id,
            start_mono_ms=self._get_mono_ms(),
            event_name=name,
        )
        self._current_spans[span_id] = ctx

        # Emit start event
        self.emit(
            start_event,
            turn_id=turn_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            payload=start_payload,
        )

        error = None
        try:
            yield span_id
        except Exception as e:
            error = e
            raise
        finally:
            # Calculate duration
            duration_ms = self._get_mono_ms() - ctx.start_mono_ms

            # Emit end event
            end_payload = {"duration_ms": round(duration_ms, 2)}
            if error:
                end_payload["error"] = str(error)

            self.emit(
                end_event,
                turn_id=turn_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                payload=end_payload,
            )

            # Clean up span context
            del self._current_spans[span_id]

    async def start_sender(self) -> None:
        """Start the background event sender task."""
        if self._sender_task is None and self.collector_url:
            self._sender_task = asyncio.create_task(self._sender_loop())

    async def stop_sender(self) -> None:
        """Stop the background event sender task."""
        if self._sender_task:
            self._sender_task.cancel()
            try:
                await self._sender_task
            except asyncio.CancelledError:
                pass
            self._sender_task = None

    async def _sender_loop(self) -> None:
        """Background loop to send events to collector."""
        import httpx

        batch: list[TraceEvent] = []
        batch_timeout = 1.0  # seconds

        async with httpx.AsyncClient() as client:
            while True:
                try:
                    # Collect events with timeout
                    try:
                        event = await asyncio.wait_for(
                            self._event_queue.get(),
                            timeout=batch_timeout,
                        )
                        batch.append(event)
                    except asyncio.TimeoutError:
                        pass

                    # Send batch if we have events
                    if batch:
                        try:
                            await client.post(
                                f"{self.collector_url}/traces",
                                json=[e.to_dict() for e in batch],
                                timeout=5.0,
                            )
                            batch = []
                        except Exception as e:
                            logger.warning(f"Failed to send traces: {e}")

                except asyncio.CancelledError:
                    # Send remaining events before exiting
                    if batch:
                        try:
                            async with httpx.AsyncClient() as final_client:
                                await final_client.post(
                                    f"{self.collector_url}/traces",
                                    json=[e.to_dict() for e in batch],
                                    timeout=5.0,
                                )
                        except Exception:
                            pass
                    break

    def get_buffered_events(self) -> list[TraceEvent]:
        """Get buffered events (for testing)."""
        return self._event_buffer.copy()

    def clear_buffer(self) -> None:
        """Clear the event buffer."""
        self._event_buffer.clear()

    def flush_to_file(self, filepath: str) -> None:
        """Flush all buffered events to a file."""
        with open(filepath, "w") as f:
            for event in self._event_buffer:
                f.write(json.dumps(event.to_dict()) + "\n")


# Global emitter instance (can be configured at startup)
_global_emitter: Optional[TraceEmitter] = None


def get_emitter() -> Optional[TraceEmitter]:
    """Get the global trace emitter."""
    return _global_emitter


def configure_emitter(
    service: str,
    collector_url: Optional[str] = None,
    output_dir: Optional[str] = None,
    enabled: bool = True,
) -> TraceEmitter:
    """Configure and return the global trace emitter."""
    global _global_emitter
    _global_emitter = TraceEmitter(
        service=service,
        collector_url=collector_url,
        output_dir=output_dir,
        enabled=enabled,
    )
    return _global_emitter
