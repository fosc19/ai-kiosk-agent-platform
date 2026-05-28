"""Store-related MCP tools."""

from typing import Any, Optional

from mcp_tools.db.repositories import StoreRepository
from mcp_tools.db.session import get_session


def list_stores(
    category: Optional[str] = None,
    floor: Optional[int] = None,
) -> dict[str, Any]:
    """
    Lista todas las tiendas del centro comercial.

    Args:
        category: Filtrar por categoría (moda, cafe, restaurante, servicios)
        floor: Filtrar por planta (0, 1, 2)

    Returns:
        Lista de tiendas con id, nombre, categoría y ubicación
    """
    with get_session() as session:
        repo = StoreRepository(session)
        stores = repo.list_all(category=category, floor=floor)

        return {
            "stores": [
                {
                    "id": store.id,
                    "name": store.name,
                    "category": store.category,
                    "floor": store.floor,
                    "location": store.location,
                }
                for store in stores
            ],
            "count": len(stores),
        }


def resolve_store(query: str) -> dict[str, Any]:
    """
    Busca una tienda por nombre o query del usuario.

    Usa búsqueda fuzzy en nombre y keywords.

    Args:
        query: Texto de búsqueda (ej: "demo_fashion", "ropa", "café")

    Returns:
        Tienda encontrada o lista de sugerencias si hay ambigüedad
    """
    with get_session() as session:
        repo = StoreRepository(session)
        best_match, confidence, alternatives = repo.resolve_by_query(query)

        if best_match:
            return {
                "found": True,
                "store": {
                    "id": best_match.id,
                    "name": best_match.name,
                    "category": best_match.category,
                },
                "confidence": round(confidence, 2),
                "alternatives": [],
            }
        else:
            return {
                "found": False,
                "store": None,
                "confidence": 0,
                "alternatives": [
                    {
                        "id": store.id,
                        "name": store.name,
                        "similarity": round(score, 2),
                    }
                    for store, score in alternatives
                ],
            }


def get_store_info(store_id: str) -> dict[str, Any]:
    """
    Obtiene información detallada de una tienda.

    Args:
        store_id: ID de la tienda (ej: "demo_fashion")

    Returns:
        Info completa: descripción, horarios, teléfono, etc.
    """
    with get_session() as session:
        repo = StoreRepository(session)
        store = repo.get_by_id(store_id)

        if not store:
            return {
                "found": False,
                "error": f"Tienda '{store_id}' no encontrada",
            }

        return {
            "found": True,
            "id": store.id,
            "name": store.name,
            "category": store.category,
            "floor": store.floor,
            "location": store.location,
            "description": store.description,
            "opening_hours": store.opening_hours,
            "phone": store.phone,
        }
