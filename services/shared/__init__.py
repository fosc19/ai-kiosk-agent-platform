"""
Shared modules for AI Kiosk services.
"""

from .tracing import TraceEmitter, TraceEvent, Events, configure_emitter

__all__ = ["TraceEmitter", "TraceEvent", "Events", "configure_emitter"]
