"""
Tracing setup for the Orchestrator service.

Configures and initializes the trace emitter with appropriate settings.
Provides a simplified wrapper for easier use in the orchestrator.
"""

import os
import sys
import uuid
from pathlib import Path
from typing import Any

# Add shared module to path
shared_path = Path(__file__).parent.parent / "shared"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

from tracing import TraceEmitter, configure_emitter, Events, generate_span_id


class OrchestratorTracer:
    """Simplified tracing wrapper for the orchestrator.

    Manages trace_id (session-level) automatically and provides
    convenient methods for emitting events with proper span hierarchy.
    """

    def __init__(self, emitter: TraceEmitter):
        self.emitter = emitter
        self._trace_id: str = ""
        self._current_turn_id: str = ""
        self._current_span_id: str = ""

    def set_trace_id(self, trace_id: str) -> None:
        """Set the trace_id for the current session."""
        self._trace_id = trace_id

    def set_turn(self, turn_id: str) -> str:
        """Set the current turn and generate a new span_id.

        Returns:
            The generated span_id for this turn
        """
        self._current_turn_id = turn_id
        self._current_span_id = generate_span_id()
        return self._current_span_id

    def emit(
        self,
        event: str | Events,
        turn_id: str | None = None,
        span_id: str | None = None,
        parent_span_id: str | None = None,
        level: str = "INFO",
        **attrs: Any,
    ) -> None:
        """Emit a trace event synchronously.

        Uses current trace_id and turn_id if not specified.
        """
        if not self.emitter.enabled:
            return

        # Use provided values or defaults
        actual_turn_id = turn_id or self._current_turn_id or "unknown"
        actual_span_id = span_id or self._current_span_id or generate_span_id()
        actual_trace_id = self._trace_id or "unknown"

        # Convert enum to string if needed
        event_name = event.value if isinstance(event, Events) else event

        self.emitter.emit_sync(
            event=event_name,
            trace_id=actual_trace_id,
            turn_id=actual_turn_id,
            span_id=actual_span_id,
            parent_span_id=parent_span_id,
            level=level,
            **attrs,
        )

    async def emit_async(
        self,
        event: str | Events,
        turn_id: str | None = None,
        span_id: str | None = None,
        parent_span_id: str | None = None,
        level: str = "INFO",
        **attrs: Any,
    ) -> None:
        """Emit a trace event asynchronously.

        Uses current trace_id and turn_id if not specified.
        """
        if not self.emitter.enabled:
            return

        # Use provided values or defaults
        actual_turn_id = turn_id or self._current_turn_id or "unknown"
        actual_span_id = span_id or self._current_span_id or generate_span_id()
        actual_trace_id = self._trace_id or "unknown"

        # Convert enum to string if needed
        event_name = event.value if isinstance(event, Events) else event

        await self.emitter.emit(
            event=event_name,
            trace_id=actual_trace_id,
            turn_id=actual_turn_id,
            span_id=actual_span_id,
            parent_span_id=parent_span_id,
            level=level,
            **attrs,
        )

    def new_span(self, parent_span_id: str | None = None) -> str:
        """Generate a new span_id for sub-operations.

        Args:
            parent_span_id: Optional parent span to link to

        Returns:
            New span_id
        """
        return generate_span_id()


def setup_tracing(
    enabled: bool = True,
    collector_url: str | None = None,
    output_dir: str | None = None,
) -> OrchestratorTracer:
    """Configure and return the trace emitter for the orchestrator.

    Args:
        enabled: Whether tracing is enabled
        collector_url: URL of the trace collector service
        output_dir: Directory to write trace files (for development)

    Returns:
        Configured OrchestratorTracer instance
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
        service="orchestrator",
        collector_url=collector_url,
        output_dir=output_dir,
        enabled=enabled,
    )

    return OrchestratorTracer(emitter)


# Re-export Events for convenience
__all__ = ["setup_tracing", "Events", "TraceEmitter", "OrchestratorTracer"]
