"""Route-related MCP tools."""

from typing import Any

from mcp_tools.db.repositories import RouteRepository, StoreRepository
from mcp_tools.db.session import get_session


def get_route(
    store_id: str,
    from_location: str = "kiosk",
) -> dict[str, Any]:
    """
    Obtiene la ruta para llegar a una tienda.

    Args:
        store_id: ID de la tienda destino
        from_location: Punto de origen (default: kiosk)

    Returns:
        Lista de pasos con instrucciones y landmarks
    """
    with get_session() as session:
        route_repo = RouteRepository(session)
        store_repo = StoreRepository(session)

        # Get store info
        store = store_repo.get_by_id(store_id)
        if not store:
            return {
                "found": False,
                "error": f"Tienda '{store_id}' no encontrada",
            }

        # Get route
        route = route_repo.get_route(store_id, from_location)
        if not route:
            return {
                "found": False,
                "error": f"No hay ruta desde '{from_location}' a '{store_id}'",
            }

        # Calculate totals
        total_distance = sum(
            step.distance_meters or 0 for step in route.steps
        )
        # Estimate ~1m/s walking speed
        estimated_time = total_distance

        return {
            "found": True,
            "store_id": store.id,
            "store_name": store.name,
            "from_location": from_location,
            "total_distance_meters": total_distance,
            "estimated_time_seconds": estimated_time,
            "steps": [
                {
                    "order": step.order,
                    "instruction": step.instruction,
                    "landmark": step.landmark,
                    "distance_meters": step.distance_meters,
                }
                for step in sorted(route.steps, key=lambda s: s.order)
            ],
        }
