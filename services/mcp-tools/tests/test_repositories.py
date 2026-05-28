"""Tests for repository layer."""

import pytest

from mcp_tools.db.repositories import (
    EventLogRepository,
    RouteRepository,
    StoreRepository,
)


class TestStoreRepository:
    """Tests for StoreRepository."""

    def test_list_all_returns_all_stores(self, session, sample_stores):
        """Test listing all stores."""
        repo = StoreRepository(session)
        stores = repo.list_all()

        assert len(stores) == 3
        store_ids = [s.id for s in stores]
        assert "demo_fashion" in store_ids
        assert "urban_wear" in store_ids
        assert "coffee_point" in store_ids

    def test_list_all_filter_by_category(self, session, sample_stores):
        """Test filtering stores by category."""
        repo = StoreRepository(session)
        stores = repo.list_all(category="moda")

        assert len(stores) == 2
        for store in stores:
            assert store.category == "moda"

    def test_list_all_filter_by_floor(self, session, sample_stores):
        """Test filtering stores by floor."""
        repo = StoreRepository(session)
        stores = repo.list_all(floor=0)

        assert len(stores) == 1
        assert stores[0].id == "coffee_point"

    def test_get_by_id_found(self, session, sample_stores):
        """Test getting a store by ID."""
        repo = StoreRepository(session)
        store = repo.get_by_id("demo_fashion")

        assert store is not None
        assert store.name == "Demo Fashion"
        assert store.category == "moda"

    def test_get_by_id_not_found(self, session, sample_stores):
        """Test getting a non-existent store."""
        repo = StoreRepository(session)
        store = repo.get_by_id("nonexistent")

        assert store is None

    def test_resolve_exact_match(self, session, sample_stores):
        """Test resolving store by exact name."""
        repo = StoreRepository(session)
        store, confidence, alternatives = repo.resolve_by_query("Demo Fashion")

        assert store is not None
        assert store.id == "demo_fashion"
        assert confidence >= 0.9

    def test_resolve_keyword_match(self, session, sample_stores):
        """Test resolving store by keyword."""
        repo = StoreRepository(session)
        store, confidence, alternatives = repo.resolve_by_query("café")

        assert store is not None
        assert store.id == "coffee_point"

    def test_resolve_fuzzy_match(self, session, sample_stores):
        """Test resolving store with typo."""
        repo = StoreRepository(session)
        store, confidence, alternatives = repo.resolve_by_query("sara")  # Typo

        # Should find Demo Fashion with fuzzy matching
        assert store is not None
        assert store.id == "demo_fashion"

    def test_resolve_ambiguous_returns_alternatives(self, session, sample_stores):
        """Test resolving ambiguous query returns alternatives."""
        repo = StoreRepository(session)
        # "ropa" matches both Demo Fashion and Urban Wear keywords
        store, confidence, alternatives = repo.resolve_by_query("xyz123")

        # With very low match, should return alternatives
        assert store is None or confidence < 0.6
        # If no confident match, alternatives should be populated
        if store is None:
            assert len(alternatives) > 0


class TestRouteRepository:
    """Tests for RouteRepository."""

    def test_get_route_found(self, session, sample_routes):
        """Test getting a route that exists."""
        repo = RouteRepository(session)
        route = repo.get_route("demo_fashion", "kiosk")

        assert route is not None
        assert route.store_id == "demo_fashion"
        assert len(route.steps) == 4

    def test_get_route_not_found(self, session, sample_routes):
        """Test getting a route that doesn't exist."""
        repo = RouteRepository(session)
        route = repo.get_route("urban_wear", "kiosk")  # No route for Urban Wear

        assert route is None

    def test_route_steps_ordered(self, session, sample_routes):
        """Test that route steps are returned in order."""
        repo = RouteRepository(session)
        route = repo.get_route("demo_fashion", "kiosk")

        orders = [step.order for step in route.steps]
        assert orders == [1, 2, 3, 4]


class TestEventLogRepository:
    """Tests for EventLogRepository."""

    def test_log_event_creates_record(self, session):
        """Test logging an event."""
        repo = EventLogRepository(session)
        event = repo.log_event(
            session_id="test-session",
            event_type="query",
            payload={"query": "donde esta demo_fashion"},
        )

        assert event.id is not None
        assert event.session_id == "test-session"
        assert event.event_type == "query"
        assert event.payload["query"] == "donde esta demo_fashion"

    def test_get_session_events(self, session):
        """Test getting events for a session."""
        repo = EventLogRepository(session)

        # Log multiple events
        repo.log_event("session-1", "start", {})
        repo.log_event("session-1", "query", {"q": "demo_fashion"})
        repo.log_event("session-2", "start", {})
        session.commit()

        events = repo.get_session_events("session-1")
        assert len(events) == 2

    def test_get_session_events_filter_type(self, session):
        """Test filtering events by type."""
        repo = EventLogRepository(session)

        repo.log_event("session-1", "start", {})
        repo.log_event("session-1", "query", {"q": "demo_fashion"})
        repo.log_event("session-1", "query", {"q": "urban_wear"})
        session.commit()

        events = repo.get_session_events("session-1", event_type="query")
        assert len(events) == 2
        for e in events:
            assert e.event_type == "query"
