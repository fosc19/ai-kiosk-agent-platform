"""Pytest configuration and fixtures."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from mcp_tools.db.models import Base, Route, RouteStep, Store


@pytest.fixture(scope="session")
def engine():
    """Create in-memory SQLite engine for testing."""
    # Use SQLite for testing (simpler setup)
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    """Create a new session for each test."""
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Clear all tables before each test
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()

    yield session
    session.close()


@pytest.fixture
def sample_stores(session):
    """Create sample stores for testing."""
    stores = [
        Store(
            id="demo_fashion",
            name="Demo Fashion",
            category="moda",
            floor=1,
            location="Planta 1, zona norte",
            description="Tienda de moda española",
            opening_hours="10:00-22:00",
            phone="+34 912 345 678",
            keywords=["demo_fashion", "ropa", "moda", "vestidos"],
        ),
        Store(
            id="urban_wear",
            name="Urban Wear",
            category="moda",
            floor=1,
            location="Planta 1, zona sur",
            description="Moda sueca",
            opening_hours="10:00-21:30",
            phone="+34 912 345 679",
            keywords=["urban wear", "urban_wear", "ropa", "moda"],
        ),
        Store(
            id="coffee_point",
            name="Coffee Point",
            category="cafe",
            floor=0,
            location="Planta baja, entrada principal",
            description="Cafetería",
            opening_hours="08:00-22:00",
            phone="+34 912 345 680",
            keywords=["coffee_point", "café", "coffee"],
        ),
    ]

    for store in stores:
        session.add(store)
    session.commit()

    return stores


@pytest.fixture
def sample_routes(session, sample_stores):
    """Create sample routes for testing."""
    routes = []

    # Route to Demo Fashion
    route_demo_fashion = Route(store_id="demo_fashion", from_location="kiosk")
    session.add(route_demo_fashion)
    session.flush()

    steps_demo_fashion = [
        RouteStep(route_id=route_demo_fashion.id, order=1, instruction="Camina recto", distance_meters=50),
        RouteStep(route_id=route_demo_fashion.id, order=2, instruction="Gira a la derecha", landmark="fuente", distance_meters=30),
        RouteStep(route_id=route_demo_fashion.id, order=3, instruction="Sube escaleras", distance_meters=20),
        RouteStep(route_id=route_demo_fashion.id, order=4, instruction="Demo Fashion a la izquierda", distance_meters=50),
    ]
    for step in steps_demo_fashion:
        session.add(step)
    routes.append(route_demo_fashion)

    # Route to Coffee Point
    route_coffee_point = Route(store_id="coffee_point", from_location="kiosk")
    session.add(route_coffee_point)
    session.flush()

    steps_coffee_point = [
        RouteStep(route_id=route_coffee_point.id, order=1, instruction="Gira a la derecha", distance_meters=20),
        RouteStep(route_id=route_coffee_point.id, order=2, instruction="Coffee Point a la izquierda", distance_meters=40),
    ]
    for step in steps_coffee_point:
        session.add(step)
    routes.append(route_coffee_point)

    session.commit()
    return routes
