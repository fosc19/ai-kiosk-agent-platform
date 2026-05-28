"""
AI Kiosk Tracing Module - Distributed tracing for the kiosk system.

Usage:
    from tracing import TraceEmitter, TraceEvent

    emitter = TraceEmitter(service="orchestrator", collector_url="http://localhost:9002")
    emitter.emit("turn_start", turn_id="turn-123", payload={"text": "Hola"})
"""

from .models import TraceEvent, Violation, GoldenFlow, SLA
from .emitter import TraceEmitter
from .collector import TraceCollectorClient

__all__ = [
    "TraceEvent",
    "Violation",
    "GoldenFlow",
    "SLA",
    "TraceEmitter",
    "TraceCollectorClient",
]
