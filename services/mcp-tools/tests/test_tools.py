"""Tests for MCP tools (integration with repositories)."""

import pytest
from unittest.mock import patch, MagicMock

from mcp_tools.db.repositories import StoreRepository, RouteRepository


class TestListStores:
    """Tests for list_stores tool."""

    def test_list_stores_returns_all(self, session, sample_stores):
        """Test list_stores returns all stores."""
        from mcp_tools.tools.stores import list_stores

        # Mock get_session to return our test session
        with patch("mcp_tools.tools.stores.get_session") as mock_get_session:
            mock_get_session.return_value.__enter__ = MagicMock(return_value=session)
            mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

            result = list_stores()

        assert result["count"] == 3
        assert len(result["stores"]) == 3

    def test_list_stores_filter_category(self, session, sample_stores):
        """Test list_stores with category filter."""
        from mcp_tools.tools.stores import list_stores

        with patch("mcp_tools.tools.stores.get_session") as mock_get_session:
            mock_get_session.return_value.__enter__ = MagicMock(return_value=session)
            mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

            result = list_stores(category="cafe")

        assert result["count"] == 1
        assert result["stores"][0]["id"] == "coffee_point"


class TestResolveStore:
    """Tests for resolve_store tool."""

    def test_resolve_store_found(self, session, sample_stores):
        """Test resolve_store finds store."""
        from mcp_tools.tools.stores import resolve_store

        with patch("mcp_tools.tools.stores.get_session") as mock_get_session:
            mock_get_session.return_value.__enter__ = MagicMock(return_value=session)
            mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

            result = resolve_store("demo_fashion")

        assert result["found"] is True
        assert result["store"]["id"] == "demo_fashion"
        assert result["confidence"] >= 0.6


class TestGetStoreInfo:
    """Tests for get_store_info tool."""

    def test_get_store_info_found(self, session, sample_stores):
        """Test get_store_info returns full info."""
        from mcp_tools.tools.stores import get_store_info

        with patch("mcp_tools.tools.stores.get_session") as mock_get_session:
            mock_get_session.return_value.__enter__ = MagicMock(return_value=session)
            mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

            result = get_store_info("demo_fashion")

        assert result["found"] is True
        assert result["id"] == "demo_fashion"
        assert result["name"] == "Demo Fashion"
        assert result["opening_hours"] == "10:00-22:00"
        assert result["description"] is not None

    def test_get_store_info_not_found(self, session, sample_stores):
        """Test get_store_info with unknown store."""
        from mcp_tools.tools.stores import get_store_info

        with patch("mcp_tools.tools.stores.get_session") as mock_get_session:
            mock_get_session.return_value.__enter__ = MagicMock(return_value=session)
            mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

            result = get_store_info("unknown")

        assert result["found"] is False
        assert "error" in result


class TestGetRoute:
    """Tests for get_route tool."""

    def test_get_route_found(self, session, sample_routes):
        """Test get_route returns route with steps."""
        from mcp_tools.tools.routes import get_route

        with patch("mcp_tools.tools.routes.get_session") as mock_get_session:
            mock_get_session.return_value.__enter__ = MagicMock(return_value=session)
            mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

            result = get_route("demo_fashion")

        assert result["found"] is True
        assert result["store_id"] == "demo_fashion"
        assert result["store_name"] == "Demo Fashion"
        assert len(result["steps"]) == 4
        assert result["total_distance_meters"] == 150  # 50+30+20+50

    def test_get_route_not_found(self, session, sample_routes):
        """Test get_route with no route available."""
        from mcp_tools.tools.routes import get_route

        with patch("mcp_tools.tools.routes.get_session") as mock_get_session:
            mock_get_session.return_value.__enter__ = MagicMock(return_value=session)
            mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

            result = get_route("urban_wear")  # No route for Urban Wear

        assert result["found"] is False
        assert "error" in result
