"""Tests for MCPToolsClient - HTTP client for MCP Tools service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "services" / "orchestrator"))

from mcp_client import MCPToolsClient


class TestMCPToolsClient:
    """Tests for MCPToolsClient."""

    @pytest.fixture
    def client(self):
        """Create MCPToolsClient instance."""
        return MCPToolsClient(base_url="http://localhost:9002", timeout=5.0)

    @pytest.fixture
    def mock_response(self):
        """Create a mock HTTP response."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"success": True}
        return response

    # === Initialization ===

    def test_init_strips_trailing_slash(self):
        """Test that trailing slash is stripped from base URL."""
        client = MCPToolsClient(base_url="http://localhost:9002/")
        assert client.base_url == "http://localhost:9002"

    def test_init_default_timeout(self):
        """Test default timeout is set."""
        client = MCPToolsClient(base_url="http://localhost:9002")
        assert client.timeout == 10.0

    def test_init_custom_timeout(self):
        """Test custom timeout is set."""
        client = MCPToolsClient(base_url="http://localhost:9002", timeout=30.0)
        assert client.timeout == 30.0

    # === HTTP Client Management ===

    @pytest.mark.asyncio
    async def test_get_client_creates_client(self, client):
        """Test that _get_client creates an AsyncClient."""
        http_client = await client._get_client()
        assert http_client is not None
        assert isinstance(http_client, httpx.AsyncClient)
        await client.close()

    @pytest.mark.asyncio
    async def test_get_client_reuses_client(self, client):
        """Test that _get_client reuses existing client."""
        http_client1 = await client._get_client()
        http_client2 = await client._get_client()
        assert http_client1 is http_client2
        await client.close()

    @pytest.mark.asyncio
    async def test_close_closes_client(self, client):
        """Test that close properly closes the client."""
        await client._get_client()
        assert client._client is not None
        await client.close()
        assert client._client is None

    # === List Stores ===

    @pytest.mark.asyncio
    async def test_list_stores_success(self, client):
        """Test list_stores returns store list."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "stores": [
                {"id": "demo_fashion", "name": "Demo Fashion", "category": "moda", "floor": 1},
                {"id": "urban_wear", "name": "Urban Wear", "category": "moda", "floor": 1},
            ],
            "count": 2,
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            result = await client.list_stores()

        assert result["count"] == 2
        assert len(result["stores"]) == 2

    @pytest.mark.asyncio
    async def test_list_stores_with_category_filter(self, client):
        """Test list_stores with category filter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"stores": [], "count": 0}
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            await client.list_stores(category="cafe")

            mock_http_client.post.assert_called_once()
            call_args = mock_http_client.post.call_args
            assert call_args[1]["json"]["category"] == "cafe"

    @pytest.mark.asyncio
    async def test_list_stores_with_floor_filter(self, client):
        """Test list_stores with floor filter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"stores": [], "count": 0}
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            await client.list_stores(floor=2)

            call_args = mock_http_client.post.call_args
            assert call_args[1]["json"]["floor"] == 2

    # === Resolve Store ===

    @pytest.mark.asyncio
    async def test_resolve_store_found(self, client):
        """Test resolve_store when store is found."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "found": True,
            "store": {"id": "demo_fashion", "name": "Demo Fashion"},
            "confidence": 0.95,
            "alternatives": [],
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            result = await client.resolve_store("demo_fashion")

        assert result["found"] is True
        assert result["store"]["id"] == "demo_fashion"
        assert result["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_resolve_store_not_found(self, client):
        """Test resolve_store when store is not found."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "found": False,
            "store": None,
            "confidence": 0.0,
            "alternatives": [{"name": "Demo Fashion", "similarity": 0.3}],
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            result = await client.resolve_store("xyz")

        assert result["found"] is False
        assert len(result["alternatives"]) > 0

    # === Get Store Info ===

    @pytest.mark.asyncio
    async def test_get_store_info_found(self, client):
        """Test get_store_info when store exists."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "found": True,
            "id": "demo_fashion",
            "name": "Demo Fashion",
            "description": "Tienda de moda",
            "opening_hours": "10:00-22:00",
            "floor": 1,
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            result = await client.get_store_info("demo_fashion")

        assert result["found"] is True
        assert result["name"] == "Demo Fashion"
        assert result["opening_hours"] == "10:00-22:00"

    @pytest.mark.asyncio
    async def test_get_store_info_not_found(self, client):
        """Test get_store_info when store doesn't exist."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "found": False,
            "error": "Store not found",
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            result = await client.get_store_info("unknown")

        assert result["found"] is False
        assert "error" in result

    # === Get Route ===

    @pytest.mark.asyncio
    async def test_get_route_found(self, client):
        """Test get_route when route exists."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "found": True,
            "store_id": "demo_fashion",
            "store_name": "Demo Fashion",
            "steps": [
                {"order": 1, "instruction": "Camina recto"},
                {"order": 2, "instruction": "Gira a la derecha"},
            ],
            "total_distance_meters": 100,
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            result = await client.get_route("demo_fashion")

        assert result["found"] is True
        assert len(result["steps"]) == 2
        assert result["total_distance_meters"] == 100

    @pytest.mark.asyncio
    async def test_get_route_custom_from_location(self, client):
        """Test get_route with custom from_location."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"found": True, "steps": []}
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            await client.get_route("demo_fashion", from_location="entrance_b")

            call_args = mock_http_client.post.call_args
            assert call_args[1]["json"]["from_location"] == "entrance_b"

    # === Log Event ===

    @pytest.mark.asyncio
    async def test_log_event_success(self, client):
        """Test log_event sends event correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "logged": True,
            "timestamp": "2024-01-15T10:30:00Z",
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            result = await client.log_event(
                session_id="session-123",
                event_type="turn_completed",
                payload={"intent": "navigate", "store_id": "demo_fashion"},
            )

        assert result["logged"] is True
        call_args = mock_http_client.post.call_args
        assert call_args[1]["json"]["session_id"] == "session-123"
        assert call_args[1]["json"]["event_type"] == "turn_completed"

    # === Health Check ===

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, client):
        """Test health_check when service is healthy."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            result = await client.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, client):
        """Test health_check when service is unhealthy."""
        mock_response = MagicMock()
        mock_response.status_code = 503

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            result = await client.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_connection_error(self, client):
        """Test health_check on connection error."""
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.get = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_get_client.return_value = mock_http_client

            result = await client.health_check()

        assert result is False

    # === Error Handling ===

    @pytest.mark.asyncio
    async def test_timeout_error_raises(self, client):
        """Test that timeout errors are raised."""
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(
                side_effect=httpx.TimeoutException("Request timed out")
            )
            mock_get_client.return_value = mock_http_client

            with pytest.raises(httpx.TimeoutException):
                await client.list_stores()

    @pytest.mark.asyncio
    async def test_http_status_error_raises(self, client):
        """Test that HTTP status errors are raised."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Internal Server Error",
            request=MagicMock(),
            response=mock_response,
        )

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            with pytest.raises(httpx.HTTPStatusError):
                await client.list_stores()

    @pytest.mark.asyncio
    async def test_general_error_raises(self, client):
        """Test that general errors are raised."""
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(
                side_effect=Exception("Unknown error")
            )
            mock_get_client.return_value = mock_http_client

            with pytest.raises(Exception, match="Unknown error"):
                await client.list_stores()


class TestMCPToolsClientIntegration:
    """Integration-style tests for MCPToolsClient.

    These tests verify the URL construction and request formatting.
    """

    @pytest.mark.asyncio
    async def test_url_construction(self):
        """Test that URLs are constructed correctly."""
        client = MCPToolsClient(base_url="http://mcp.local:9002")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"stores": [], "count": 0}
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.post = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http_client

            await client.list_stores()

            call_args = mock_http_client.post.call_args
            assert call_args[0][0] == "http://mcp.local:9002/tools/list_stores"
