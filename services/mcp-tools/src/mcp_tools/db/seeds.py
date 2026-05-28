"""Database seeding script for MCP Tools."""

import json
import os
from pathlib import Path

import structlog

from mcp_tools.db.models import Route, RouteStep, Store
from mcp_tools.db.session import get_session

log = structlog.get_logger()

# Default path to seed data - check env var first, then fallback to relative path
_seeds_env = os.getenv("MCP_SEEDS_DIR")
if _seeds_env:
    SEEDS_DIR = Path(_seeds_env)
else:
    # Try common locations
    _candidates = [
        Path("/app/seeds"),  # Docker
        Path(__file__).parent.parent.parent.parent.parent.parent / "data" / "seeds",  # Dev
        Path.cwd() / "data" / "seeds",  # CWD
    ]
    SEEDS_DIR = next((p for p in _candidates if p.exists()), _candidates[-1])


def load_json(filename: str) -> list[dict]:
    """Load JSON data from seeds directory."""
    filepath = SEEDS_DIR / filename
    if not filepath.exists():
        log.warning("seed_file_not_found", filepath=str(filepath))
        return []
    with open(filepath, encoding="utf-8") as f:
        return json.load(f)


def seed_stores() -> int:
    """Seed stores table from JSON file."""
    stores_data = load_json("stores.json")
    count = 0

    with get_session() as session:
        for data in stores_data:
            existing = session.get(Store, data["id"])
            if existing:
                log.debug("store_exists", store_id=data["id"])
                continue

            store = Store(
                id=data["id"],
                name=data["name"],
                category=data["category"],
                floor=data["floor"],
                location=data["location"],
                description=data.get("description"),
                opening_hours=data["opening_hours"],
                phone=data.get("phone"),
                keywords=data.get("keywords", []),
            )
            session.add(store)
            count += 1
            log.info("store_created", store_id=store.id, name=store.name)

    return count


def seed_routes() -> int:
    """Seed routes and route_steps tables from JSON file."""
    routes_data = load_json("routes.json")
    count = 0

    with get_session() as session:
        for data in routes_data:
            # Check if route already exists
            existing = (
                session.query(Route)
                .filter_by(store_id=data["store_id"], from_location=data["from_location"])
                .first()
            )
            if existing:
                log.debug("route_exists", store_id=data["store_id"])
                continue

            route = Route(
                store_id=data["store_id"],
                from_location=data["from_location"],
            )
            session.add(route)
            session.flush()  # Get route.id

            for step_data in data["steps"]:
                step = RouteStep(
                    route_id=route.id,
                    order=step_data["order"],
                    instruction=step_data["instruction"],
                    landmark=step_data.get("landmark"),
                    distance_meters=step_data.get("distance_meters"),
                )
                session.add(step)

            count += 1
            log.info(
                "route_created",
                store_id=data["store_id"],
                steps=len(data["steps"]),
            )

    return count


def run_seeds() -> dict[str, int]:
    """Run all seed functions."""
    log.info("seeds_starting")

    results = {
        "stores": seed_stores(),
        "routes": seed_routes(),
    }

    log.info("seeds_completed", **results)
    return results


if __name__ == "__main__":
    import sys

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ]
    )

    try:
        results = run_seeds()
        print(f"\nSeeds completed: {results}")
    except Exception as e:
        print(f"Error running seeds: {e}", file=sys.stderr)
        sys.exit(1)
