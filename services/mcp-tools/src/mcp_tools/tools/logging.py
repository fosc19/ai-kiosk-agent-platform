"""Logging-related MCP tools."""

from typing import Any

from mcp_tools.db.repositories import EventLogRepository
from mcp_tools.db.session import get_session


def log_event(
    session_id: str,
    event_type: str,
    payload: dict,
) -> dict[str, Any]:
    """
    Registra un evento en el log de sesión.

    Args:
        session_id: ID de la sesión actual
        event_type: Tipo de evento (query, route_shown, error, etc.)
        payload: Datos del evento

    Returns:
        Confirmación con timestamp
    """
    with get_session() as session:
        repo = EventLogRepository(session)
        event = repo.log_event(
            session_id=session_id,
            event_type=event_type,
            payload=payload,
        )

        return {
            "success": True,
            "event_id": event.id,
            "timestamp": event.timestamp.isoformat() if event.timestamp else None,
        }
