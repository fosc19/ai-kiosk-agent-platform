"""Tests for MCPRouter with LLM-only classification (F6)."""

import pytest
from unittest.mock import AsyncMock

from router_mcp import MCPRouter, RouterResult
from llm_router import Intent
from llm_adapter import MockLLMAdapter
from conversation_memory import ConversationMemory, ConversationContext


class TestMCPRouter:
    """Tests for MCPRouter."""

    @pytest.fixture
    def mock_mcp_client(self):
        """Create mock MCP client."""
        client = AsyncMock()
        client.health_check = AsyncMock(return_value=True)
        client.list_stores = AsyncMock(return_value={
            "stores": [
                {"id": "demo_fashion", "name": "Demo Fashion", "category": "moda", "floor": 1},
                {"id": "urban_wear", "name": "Urban Wear", "category": "moda", "floor": 1},
                {"id": "coffee_point", "name": "Coffee Point", "category": "cafeteria", "floor": 0},
            ],
            "count": 3,
        })
        client.resolve_store = AsyncMock(return_value={
            "found": True,
            "store": {"id": "demo_fashion", "name": "Demo Fashion"},
            "confidence": 1.0,
        })
        client.get_route = AsyncMock(return_value={
            "found": True,
            "store_id": "demo_fashion",
            "store_name": "Demo Fashion",
            "steps": [
                {"order": 1, "instruction": "Camina recto hacia la fuente"},
                {"order": 2, "instruction": "Gira a la derecha"},
            ],
        })
        client.get_store_info = AsyncMock(return_value={
            "found": True,
            "id": "demo_fashion",
            "name": "Demo Fashion",
            "location": "Planta 1",
            "description": "Tienda de moda",
        })
        client.log_event = AsyncMock(return_value={"logged": True})
        client.close = AsyncMock()
        return client

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM adapter."""
        return MockLLMAdapter()

    @pytest.fixture
    def router(self, mock_mcp_client, mock_llm):
        """Create MCPRouter with mock dependencies."""
        return MCPRouter(
            mcp_client=mock_mcp_client,
            llm_adapter=mock_llm,
            use_llm=True,
        )

    @pytest.fixture
    def router_no_llm(self, mock_mcp_client):
        """Create MCPRouter without LLM."""
        return MCPRouter(
            mcp_client=mock_mcp_client,
            llm_adapter=None,
            use_llm=False,
        )

    @pytest.mark.asyncio
    async def test_route_greeting(self, router):
        """Test routing greeting intent."""
        result = await router.route("hola buenos días", "session-1")
        assert result.intent == Intent.GREETING
        assert "Sofía" in result.response_text

    @pytest.mark.asyncio
    async def test_route_goodbye(self, router):
        """Test routing goodbye intent."""
        result = await router.route("adiós hasta luego", "session-1")
        assert result.intent == Intent.GOODBYE
        assert "luego" in result.response_text.lower()

    @pytest.mark.asyncio
    async def test_route_help(self, router):
        """Test routing help intent."""
        result = await router.route("necesito ayuda", "session-1")
        assert result.intent == Intent.HELP
        assert "ayudar" in result.response_text.lower()

    @pytest.mark.asyncio
    async def test_route_list_stores(self, router, mock_mcp_client):
        """Test routing list stores intent."""
        result = await router.route("qué tiendas hay", "session-1")
        assert result.intent == Intent.LIST_STORES
        mock_mcp_client.list_stores.assert_called()
        assert "Demo Fashion" in result.response_text

    @pytest.mark.asyncio
    async def test_route_navigate(self, router, mock_mcp_client):
        """Test routing navigate intent."""
        result = await router.route("dónde está Demo Fashion", "session-1")
        assert result.intent == Intent.NAVIGATE
        mock_mcp_client.resolve_store.assert_called()
        mock_mcp_client.get_route.assert_called()
        assert result.route_data is not None
        assert "Demo Fashion" in result.response_text

    @pytest.mark.asyncio
    async def test_route_navigate_store_not_found(self, router, mock_mcp_client):
        """Test navigation when store not found."""
        mock_mcp_client.resolve_store.return_value = {
            "found": False,
            "store": None,
            "alternatives": [{"name": "Demo Fashion", "similarity": 0.5}],
        }
        result = await router.route("dónde está xyz", "session-1")
        assert result.intent == Intent.CLARIFY
        assert "Demo Fashion" in result.response_text  # Should suggest alternatives

    @pytest.mark.asyncio
    async def test_route_store_info(self, router, mock_mcp_client):
        """Test routing store info intent."""
        result = await router.route("información de Demo Fashion", "session-1")
        assert result.intent == Intent.STORE_INFO
        mock_mcp_client.get_store_info.assert_called()
        assert "Demo Fashion" in result.response_text

    @pytest.mark.asyncio
    async def test_route_empty_text(self, router):
        """Test routing empty text."""
        result = await router.route("", "session-1")
        assert result.intent == Intent.UNKNOWN
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_route_without_llm(self, router_no_llm):
        """Test routing without LLM adapter (falls back to rules)."""
        result = await router_no_llm.route("hola", "session-1")
        assert result.intent == Intent.GREETING
        assert result.classification_source == "rules_fallback"

    @pytest.mark.asyncio
    async def test_catalog_loaded_on_first_route(self, router, mock_mcp_client):
        """Test that catalog is loaded on first route call."""
        await router.route("hola", "session-1")
        mock_mcp_client.list_stores.assert_called()
        assert len(router._store_names) == 3

    @pytest.mark.asyncio
    async def test_latency_tracked(self, router):
        """Test that latency is tracked."""
        result = await router.route("hola", "session-1")
        assert result.latency_ms > 0

    @pytest.mark.asyncio
    async def test_log_event_called(self, router, mock_mcp_client):
        """Test that events are logged."""
        await router.route("hola", "session-1")
        mock_mcp_client.log_event.assert_called()

    @pytest.mark.asyncio
    async def test_mcp_error_handling(self, router, mock_mcp_client):
        """Test handling of MCP errors."""
        mock_mcp_client.list_stores.side_effect = Exception("Connection failed")
        result = await router.route("qué tiendas hay", "session-1")
        # Should handle gracefully
        assert "no puedo acceder" in result.response_text.lower() or result.intent == Intent.LIST_STORES


class TestRouterResult:
    """Tests for RouterResult dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = RouterResult(
            intent=Intent.GREETING,
            params={},
            response_text="Hola",
        )
        assert result.confidence == 1.0
        assert result.route_data is None
        assert result.classification_source == "rules"
        assert result.latency_ms == 0.0

    def test_with_all_values(self):
        """Test with all values."""
        result = RouterResult(
            intent=Intent.NAVIGATE,
            params={"store_id": "demo_fashion"},
            response_text="Para llegar a Demo Fashion...",
            confidence=0.9,
            route_data={"steps": []},
            classification_source="llm",
            latency_ms=500.0,
        )
        assert result.intent == Intent.NAVIGATE
        assert result.route_data is not None
        assert result.classification_source == "llm"
