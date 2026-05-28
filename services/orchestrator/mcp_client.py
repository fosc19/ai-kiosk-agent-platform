"""MCP Tools HTTP Client for Orchestrator."""

from typing import Any, Optional

import httpx
import structlog

log = structlog.get_logger()


class MCPToolsClient:
    """HTTP client for MCP Tools service."""

    def __init__(self, base_url: str, timeout: float = 10.0):
        """Initialize client.

        Args:
            base_url: Base URL of MCP Tools service (e.g., http://localhost:9002)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _post(self, endpoint: str, data: dict) -> dict[str, Any]:
        """Make POST request to MCP Tools service."""
        client = await self._get_client()
        url = f"{self.base_url}/tools/{endpoint}"

        try:
            response = await client.post(url, json=data)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            log.error("mcp_tools_timeout", endpoint=endpoint)
            raise
        except httpx.HTTPStatusError as e:
            log.error("mcp_tools_http_error", endpoint=endpoint, status=e.response.status_code)
            raise
        except Exception as e:
            log.error("mcp_tools_error", endpoint=endpoint, error=str(e))
            raise

    async def list_stores(
        self,
        category: Optional[str] = None,
        floor: Optional[int] = None,
    ) -> dict[str, Any]:
        """List all stores.

        Args:
            category: Filter by category (moda, cafe, etc.)
            floor: Filter by floor (0, 1, 2)

        Returns:
            Dict with stores list and count
        """
        data = {}
        if category is not None:
            data["category"] = category
        if floor is not None:
            data["floor"] = floor

        result = await self._post("list_stores", data)
        log.info("mcp_list_stores", count=result.get("count", 0))
        return result

    async def resolve_store(self, query: str) -> dict[str, Any]:
        """Resolve a store by fuzzy search.

        Args:
            query: Search query (store name or keywords)

        Returns:
            Dict with found flag, store info, confidence, and alternatives
        """
        result = await self._post("resolve_store", {"query": query})
        log.info(
            "mcp_resolve_store",
            query=query,
            found=result.get("found", False),
            confidence=result.get("confidence", 0),
        )
        return result

    async def get_store_info(self, store_id: str) -> dict[str, Any]:
        """Get detailed store information.

        Args:
            store_id: Store ID

        Returns:
            Dict with store details
        """
        result = await self._post("get_store_info", {"store_id": store_id})
        log.info("mcp_get_store_info", store_id=store_id, found=result.get("found", False))
        return result

    async def get_route(
        self,
        store_id: str,
        from_location: str = "kiosk",
    ) -> dict[str, Any]:
        """Get route to a store.

        Args:
            store_id: Destination store ID
            from_location: Starting location

        Returns:
            Dict with route steps and metadata
        """
        result = await self._post("get_route", {
            "store_id": store_id,
            "from_location": from_location,
        })
        log.info(
            "mcp_get_route",
            store_id=store_id,
            found=result.get("found", False),
            steps=len(result.get("steps", [])),
        )
        return result

    async def log_event(
        self,
        session_id: str,
        event_type: str,
        payload: dict,
    ) -> dict[str, Any]:
        """Log an event.

        Args:
            session_id: Session ID
            event_type: Event type
            payload: Event data

        Returns:
            Dict with success flag and timestamp
        """
        result = await self._post("log_event", {
            "session_id": session_id,
            "event_type": event_type,
            "payload": payload,
        })
        return result

    async def health_check(self) -> bool:
        """Check if MCP Tools service is healthy."""
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/healthz")
            return response.status_code == 200
        except Exception:
            return False
