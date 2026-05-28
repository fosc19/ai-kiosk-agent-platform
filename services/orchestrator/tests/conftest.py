"""Pytest configuration and fixtures for orchestrator tests."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from llm_adapter import MockLLMAdapter, LLMClassification
from policies import PolicyEngine


@pytest.fixture
def mock_llm_adapter():
    """Create a mock LLM adapter."""
    return MockLLMAdapter()


@pytest.fixture
def sample_stores():
    """Sample store data for testing."""
    return [
        {"id": "demo_fashion", "name": "Demo Fashion", "category": "moda", "floor": 1},
        {"id": "urban_wear", "name": "Urban Wear", "category": "moda", "floor": 1},
        {"id": "coffee_point", "name": "Coffee Point", "category": "cafeteria", "floor": 0},
    ]


@pytest.fixture
def store_names(sample_stores):
    """Store names from sample stores."""
    return [s["name"] for s in sample_stores]


@pytest.fixture
def store_ids(sample_stores):
    """Store IDs from sample stores."""
    return {s["id"] for s in sample_stores}


@pytest.fixture
def policy_engine(store_ids, store_names):
    """Create a policy engine with sample catalog."""
    return PolicyEngine(
        catalog_store_ids=store_ids,
        catalog_store_names=set(store_names),
    )


@pytest.fixture
def mock_mcp_client():
    """Create a mock MCP client."""
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
            {"order": 1, "instruction": "Camina recto"},
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
