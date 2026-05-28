"""
Tracing setup for the Speech service.

Configures and initializes the trace emitter with appropriate settings.
"""

import os
import sys
from pathlib import Path
from typing import Any

# Add shared module to path
shared_path = Path(__file__).parent.parent / "shared"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from tracing import TraceEmitter, configure_emitter, Events, generate_span_id


class SpeechTracer:
    """Simplified tracing wrapper for the speech service.

    Provides convenient methods for emitting ASR and TTS trace events.
    """

    def __init__(self, emitter: TraceEmitter):
        self.emitter = emitter

    def emit(
        self,
        event: str | Events,
        trace_id: str,
        turn_id: str,
        span_id: str | None = None,
        parent_span_id: str | None = None,
        level: str = "INFO",
        **attrs: Any,
    ) -> None:
        """Emit a trace event synchronously."""
        if not self.emitter.enabled:
            return

        actual_span_id = span_id or generate_span_id()
        event_name = event.value if isinstance(event, Events) else event

        self.emitter.emit_sync(
            event=event_name,
            trace_id=trace_id,
            turn_id=turn_id,
            span_id=actual_span_id,
            parent_span_id=parent_span_id,
            level=level,
            **attrs,
        )

    async def emit_async(
        self,
        event: str | Events,
        trace_id: str,
        turn_id: str,
        span_id: str | None = None,
        parent_span_id: str | None = None,
        level: str = "INFO",
        **attrs: Any,
    ) -> None:
        """Emit a trace event asynchronously."""
        if not self.emitter.enabled:
            return

        actual_span_id = span_id or generate_span_id()
        event_name = event.value if isinstance(event, Events) else event

        await self.emitter.emit(
            event=event_name,
            trace_id=trace_id,
            turn_id=turn_id,
            span_id=actual_span_id,
            parent_span_id=parent_span_id,
            level=level,
            **attrs,
        )

    def new_span(self) -> str:
        """Generate a new span_id."""
        return generate_span_id()


def setup_tracing(
    enabled: bool = True,
    collector_url: str | None = None,
    output_dir: str | None = None,
) -> SpeechTracer:
    """Configure and return the trace emitter for the speech service.

    Args:
        enabled: Whether tracing is enabled
        collector_url: URL of the trace collector service
        output_dir: Directory to write trace files (for development)

    Returns:
        Configured SpeechTracer instance
    """
    # Use environment variables as defaults
    if collector_url is None:
        collector_url = os.getenv("TRACE_COLLECTOR_URL")

    if output_dir is None:
        output_dir = os.getenv("TRACE_OUTPUT_DIR", "data/traces")

    # Check if tracing is enabled via environment
    env_enabled = os.getenv("TRACING_ENABLED", "true").lower() == "true"
    enabled = enabled and env_enabled

    emitter = configure_emitter(
        service="speech",
        collector_url=collector_url,
        output_dir=output_dir,
        enabled=enabled,
    )

    return SpeechTracer(emitter)


# Re-export Events for convenience
__all__ = ["setup_tracing", "Events", "SpeechTracer"]
