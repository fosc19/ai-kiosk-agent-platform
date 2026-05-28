"""MCP Server with tool registration."""

from typing import Any, Optional

import structlog
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from mcp_tools.tools import (
    get_route,
    get_store_info,
    list_stores,
    log_event,
    resolve_store,
)

log = structlog.get_logger()

# Create MCP server instance
mcp_server = Server("mcp-tools")


# Tool definitions with JSON schemas
TOOLS = [
    Tool(
        name="list_stores",
        description="Lista todas las tiendas del centro comercial. Puede filtrar por categoría (moda, cafe, restaurante) o por planta (0, 1, 2).",
        inputSchema={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Filtrar por categoría (moda, cafe, restaurante, servicios)",
                },
                "floor": {
                    "type": "integer",
                    "description": "Filtrar por planta (0=baja, 1, 2)",
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="resolve_store",
        description="Busca una tienda por nombre o query del usuario. Usa búsqueda fuzzy para encontrar la mejor coincidencia.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Texto de búsqueda (ej: 'demo_fashion', 'ropa', 'café')",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="get_store_info",
        description="Obtiene información detallada de una tienda: descripción, horarios, teléfono, ubicación.",
        inputSchema={
            "type": "object",
            "properties": {
                "store_id": {
                    "type": "string",
                    "description": "ID de la tienda (ej: 'demo_fashion', 'urban_wear', 'coffee_point')",
                },
            },
            "required": ["store_id"],
        },
    ),
    Tool(
        name="get_route",
        description="Obtiene la ruta paso a paso para llegar a una tienda desde el kiosk.",
        inputSchema={
            "type": "object",
            "properties": {
                "store_id": {
                    "type": "string",
                    "description": "ID de la tienda destino",
                },
                "from_location": {
                    "type": "string",
                    "description": "Punto de origen (default: 'kiosk')",
                    "default": "kiosk",
                },
            },
            "required": ["store_id"],
        },
    ),
    Tool(
        name="log_event",
        description="Registra un evento en el log de sesión para analytics.",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "ID de la sesión actual",
                },
                "event_type": {
                    "type": "string",
                    "description": "Tipo de evento (query, route_shown, error, etc.)",
                },
                "payload": {
                    "type": "object",
                    "description": "Datos adicionales del evento",
                },
            },
            "required": ["session_id", "event_type", "payload"],
        },
    ),
]


@mcp_server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """Return list of available tools."""
    return TOOLS


@mcp_server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    log.info("tool_call", tool=name, arguments=arguments)

    try:
        if name == "list_stores":
            result = list_stores(
                category=arguments.get("category"),
                floor=arguments.get("floor"),
            )
        elif name == "resolve_store":
            result = resolve_store(query=arguments["query"])
        elif name == "get_store_info":
            result = get_store_info(store_id=arguments["store_id"])
        elif name == "get_route":
            result = get_route(
                store_id=arguments["store_id"],
                from_location=arguments.get("from_location", "kiosk"),
            )
        elif name == "log_event":
            result = log_event(
                session_id=arguments["session_id"],
                event_type=arguments["event_type"],
                payload=arguments["payload"],
            )
        else:
            result = {"error": f"Unknown tool: {name}"}

        log.info("tool_result", tool=name, result=result)

        import json
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    except Exception as e:
        log.error("tool_error", tool=name, error=str(e))
        import json
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def run_server():
    """Run the MCP server."""
    log.info("mcp_server_starting")
    async with stdio_server() as (read_stream, write_stream):
        await mcp_server.run(
            read_stream,
            write_stream,
            mcp_server.create_initialization_options(),
        )
