"""Repository layer for database access."""

from datetime import datetime
from typing import Optional

from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from mcp_tools.config import settings
from mcp_tools.db.models import EventLog, Route, RouteStep, Store


class StoreRepository:
    """Repository for Store operations."""

    def __init__(self, session: Session):
        self.session = session

    def list_all(
        self,
        category: Optional[str] = None,
        floor: Optional[int] = None,
    ) -> list[Store]:
        """List all stores, optionally filtered by category or floor."""
        query = select(Store)

        if category is not None:
            query = query.where(Store.category == category)
        if floor is not None:
            query = query.where(Store.floor == floor)

        query = query.order_by(Store.name)
        return list(self.session.scalars(query))

    def get_by_id(self, store_id: str) -> Optional[Store]:
        """Get a store by its ID."""
        return self.session.get(Store, store_id)

    def resolve_by_query(
        self,
        query: str,
        threshold: float = None,
    ) -> tuple[Optional[Store], float, list[tuple[Store, float]]]:
        """
        Resolve a store by fuzzy matching on name and keywords.

        Returns:
            Tuple of (best_match, confidence, alternatives)
            - best_match: Store if confidence >= threshold, else None
            - confidence: Score 0-1 for best match
            - alternatives: List of (store, score) pairs if no confident match
        """
        if threshold is None:
            threshold = settings.fuzzy_threshold

        stores = self.list_all()
        if not stores:
            return None, 0.0, []

        query_lower = query.lower().strip()

        # Build choices: (search_text, store)
        choices = []
        for store in stores:
            # Match against name
            choices.append((store.name.lower(), store))
            # Match against each keyword
            for keyword in store.keywords or []:
                choices.append((keyword.lower(), store))

        # Find best matches using rapidfuzz
        search_texts = [c[0] for c in choices]
        results = process.extract(
            query_lower,
            search_texts,
            scorer=fuzz.WRatio,
            limit=10,
        )

        # Group by store and take best score for each
        store_scores: dict[str, tuple[Store, float]] = {}
        for match_text, score, idx in results:
            store = choices[idx][1]
            normalized_score = score / 100.0  # Convert to 0-1

            if store.id not in store_scores or normalized_score > store_scores[store.id][1]:
                store_scores[store.id] = (store, normalized_score)

        if not store_scores:
            return None, 0.0, []

        # Sort by score descending
        sorted_matches = sorted(
            store_scores.values(),
            key=lambda x: x[1],
            reverse=True,
        )

        best_store, best_score = sorted_matches[0]

        # If confident match, return it
        if best_score >= threshold:
            return best_store, best_score, []

        # Otherwise return alternatives
        alternatives = sorted_matches[:5]  # Top 5 alternatives
        return None, best_score, alternatives


class RouteRepository:
    """Repository for Route operations."""

    def __init__(self, session: Session):
        self.session = session

    def get_route(
        self,
        store_id: str,
        from_location: str = "kiosk",
    ) -> Optional[Route]:
        """Get route to a store from a location."""
        query = (
            select(Route)
            .options(joinedload(Route.steps))
            .where(Route.store_id == store_id)
            .where(Route.from_location == from_location)
        )
        return self.session.scalar(query)

    def get_route_with_store(
        self,
        store_id: str,
        from_location: str = "kiosk",
    ) -> Optional[tuple[Route, Store]]:
        """Get route to a store including store details."""
        query = (
            select(Route, Store)
            .join(Store)
            .options(joinedload(Route.steps))
            .where(Route.store_id == store_id)
            .where(Route.from_location == from_location)
        )
        result = self.session.execute(query).first()
        if result:
            return result.Route, result.Store
        return None


class EventLogRepository:
    """Repository for EventLog operations."""

    def __init__(self, session: Session):
        self.session = session

    def log_event(
        self,
        session_id: str,
        event_type: str,
        payload: dict,
    ) -> EventLog:
        """Log an event."""
        event = EventLog(
            session_id=session_id,
            event_type=event_type,
            payload=payload,
        )
        self.session.add(event)
        self.session.flush()
        return event

    def get_session_events(
        self,
        session_id: str,
        event_type: Optional[str] = None,
    ) -> list[EventLog]:
        """Get events for a session."""
        query = select(EventLog).where(EventLog.session_id == session_id)

        if event_type:
            query = query.where(EventLog.event_type == event_type)

        query = query.order_by(EventLog.timestamp)
        return list(self.session.scalars(query))
