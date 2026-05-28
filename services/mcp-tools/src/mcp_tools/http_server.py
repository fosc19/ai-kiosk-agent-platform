"""HTTP Server exposing MCP tools as REST endpoints."""

import time
from typing import Any, Optional

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from mcp_tools.config import settings
from mcp_tools.tools import (
    get_route,
    get_store_info,
    list_stores,
    log_event,
    resolve_store,
)

# F8: Tracing
try:
    from mcp_tools.tracing_setup import setup_tracing
    trace_emitter = setup_tracing()
except ImportError:
    trace_emitter = None

log = structlog.get_logger()

app = FastAPI(
    title="MCP Tools HTTP Server",
    description="REST API for kiosk data tools (stores, routes, logging)",
    version="0.1.0",
)


# Request/Response models
class ListStoresRequest(BaseModel):
    category: Optional[str] = None
    floor: Optional[int] = None


class ResolveStoreRequest(BaseModel):
    query: str


class GetStoreInfoRequest(BaseModel):
    store_id: str


class GetRouteRequest(BaseModel):
    store_id: str
    from_location: str = "kiosk"


class LogEventRequest(BaseModel):
    session_id: str
    event_type: str
    payload: dict


@app.get("/healthz")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "mcp-tools",
        "version": "0.1.0",
    }


@app.post("/tools/list_stores")
async def api_list_stores(request: ListStoresRequest) -> dict[str, Any]:
    """List all stores, optionally filtered."""
    log.info("api_list_stores", category=request.category, floor=request.floor)
    try:
        result = list_stores(category=request.category, floor=request.floor)
        return result
    except Exception as e:
        log.error("api_list_stores_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tools/resolve_store")
async def api_resolve_store(request: ResolveStoreRequest) -> dict[str, Any]:
    """Resolve a store by fuzzy query."""
    log.info("api_resolve_store", query=request.query)
    start_time = time.perf_counter()

    # F8: Trace call start
    if trace_emitter:
        trace_emitter.emit(
            "mcp.call_start",
            payload={"tool_name": "resolve_store", "args": {"query": request.query}}
        )

    try:
        result = resolve_store(query=request.query)

        # F8: Trace call end
        latency_ms = (time.perf_counter() - start_time) * 1000
        if trace_emitter:
            trace_emitter.emit(
                "mcp.call_end",
                payload={
                    "tool_name": "resolve_store",
                    "latency_ms": round(latency_ms, 2),
                    "result_found": result.get("found", False),
                }
            )

        return result
    except Exception as e:
        # F8: Trace error
        if trace_emitter:
            trace_emitter.emit(
                "mcp.call_error",
                payload={"tool_name": "resolve_store", "error": str(e)}
            )
        log.error("api_resolve_store_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tools/get_store_info")
async def api_get_store_info(request: GetStoreInfoRequest) -> dict[str, Any]:
    """Get detailed store information."""
    log.info("api_get_store_info", store_id=request.store_id)
    try:
        result = get_store_info(store_id=request.store_id)
        return result
    except Exception as e:
        log.error("api_get_store_info_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tools/get_route")
async def api_get_route(request: GetRouteRequest) -> dict[str, Any]:
    """Get route to a store."""
    log.info("api_get_route", store_id=request.store_id, from_location=request.from_location)
    start_time = time.perf_counter()

    # F8: Trace call start
    if trace_emitter:
        trace_emitter.emit(
            "mcp.call_start",
            payload={
                "tool_name": "get_route",
                "args": {"store_id": request.store_id, "from_location": request.from_location}
            }
        )

    try:
        result = get_route(store_id=request.store_id, from_location=request.from_location)

        # F8: Trace call end
        latency_ms = (time.perf_counter() - start_time) * 1000
        if trace_emitter:
            trace_emitter.emit(
                "mcp.call_end",
                payload={
                    "tool_name": "get_route",
                    "latency_ms": round(latency_ms, 2),
                    "result_found": result.get("found", False),
                }
            )

        return result
    except Exception as e:
        # F8: Trace error
        if trace_emitter:
            trace_emitter.emit(
                "mcp.call_error",
                payload={"tool_name": "get_route", "error": str(e)}
            )
        log.error("api_get_route_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tools/log_event")
async def api_log_event(request: LogEventRequest) -> dict[str, Any]:
    """Log an event."""
    log.info("api_log_event", session_id=request.session_id, event_type=request.event_type)
    try:
        result = log_event(
            session_id=request.session_id,
            event_type=request.event_type,
            payload=request.payload,
        )
        return result
    except Exception as e:
        log.error("api_log_event_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


def run_http_server():
    """Run the HTTP server."""
    import uvicorn

    log.info(
        "http_server_starting",
        host=settings.host,
        port=settings.port,
    )
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )
