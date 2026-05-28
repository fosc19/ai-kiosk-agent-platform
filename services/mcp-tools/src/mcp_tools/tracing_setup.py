"""
Tracing setup for the MCP Tools service.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Any

# Add shared module to path
shared_path = Path(__file__).parent.parent.parent.parent.parent / "shared"
if str(shared_path) not in sys.path:
    sys.path.insert(0, str(shared_path))

try:
    from tracing import TraceEmitter, configure_emitter, Events
except ImportError:
    # If shared module not available, create dummy objects
    TraceEmitter = None
    Events = None

    def configure_emitter(*args, **kwargs):
        return None


def setup_tracing(
    enabled: bool = True,
    collector_url: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> Optional[Any]:
    """
    Configure and return the trace emitter for MCP Tools.
    """
    if TraceEmitter is None:
        return None

    # Use environment variables as defaults
    if collector_url is None:
        collector_url = os.getenv("TRACE_COLLECTOR_URL")

    if output_dir is None:
        output_dir = os.getenv("TRACE_OUTPUT_DIR", "data/traces")

    # Check if tracing is enabled via environment
    env_enabled = os.getenv("TRACING_ENABLED", "true").lower() == "true"
    enabled = enabled and env_enabled

    emitter = configure_emitter(
        service="mcp-tools",
        collector_url=collector_url,
        output_dir=output_dir,
        enabled=enabled,
    )

    return emitter


__all__ = ["setup_tracing", "Events", "TraceEmitter"]
