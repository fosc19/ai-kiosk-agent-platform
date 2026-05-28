"""Tests for policies module."""

import pytest
from policies import (
    PolicyEngine,
    PolicyViolation,
    PolicyCheckResult,
    is_safe_intent,
    get_safe_response,
    SAFE_RESPONSES,
)


class TestPolicyEngine:
    """Tests for PolicyEngine."""

    @pytest.fixture
    def engine(self):
        """Create policy engine with sample catalog."""
        return PolicyEngine(
            catalog_store_ids={"demo_fashion", "urban_wear", "coffee_point"},
            catalog_store_names={"Demo Fashion", "Urban Wear", "Coffee Point"},
        )

    def test_init(self, engine):
        """Test engine initialization."""
        assert "demo_fashion" in engine.catalog_store_ids
        assert "demo_fashion" in engine.catalog_store_names

    def test_update_catalog(self, engine):
        """Test catalog update."""
        engine.update_catalog(
            store_ids={"new_store"},
            store_names={"New Store"},
        )
        assert "new_store" in engine.catalog_store_ids
        assert "demo_fashion" not in engine.catalog_store_ids

    def test_check_response_valid_store(self, engine):
        """Test response check with valid store."""
        result = engine.check_response(
            response_text="Demo Fashion está en la planta 1",
            intent="navigate",
            store_id="demo_fashion",
        )
        assert result.passed

    def test_check_response_invalid_store_id(self, engine):
        """Test response check with invalid store ID."""
        result = engine.check_response(
            response_text="Test response",
            intent="navigate",
            store_id="invalid_store",
        )
        assert not result.passed
        assert len(result.violations) > 0
        assert result.violations[0].policy_name == "valid_store_id"

    def test_validate_store_query_empty(self, engine):
        """Test validation of empty store query."""
        valid, message = engine.validate_store_query(None, 0.9)
        assert not valid
        assert message is not None

    def test_validate_store_query_exact_match(self, engine):
        """Test validation of exact store match."""
        valid, message = engine.validate_store_query("Demo Fashion", 0.9)
        assert valid
        assert message is None

    def test_validate_store_query_partial_match(self, engine):
        """Test validation of partial store match."""
        valid, message = engine.validate_store_query("star", 0.9)
        assert valid  # "star" is in "coffee_point"

    def test_validate_store_query_low_confidence_unknown(self, engine):
        """Test validation with low confidence and unknown store."""
        valid, message = engine.validate_store_query("xyz", 0.5)
        assert not valid
        assert "específico" in message.lower()

    def test_get_clarification_response_navigate(self, engine):
        """Test clarification for navigate intent."""
        response = engine.get_clarification_response(
            "navigate",
            ["Demo Fashion", "Urban Wear", "Coffee Point"],
        )
        assert "qué tienda" in response.lower()
        assert "Demo Fashion" in response

    def test_get_clarification_response_store_info(self, engine):
        """Test clarification for store_info intent."""
        response = engine.get_clarification_response(
            "store_info",
            ["Demo Fashion"],
        )
        assert "información" in response.lower()

    def test_get_clarification_response_empty_stores(self, engine):
        """Test clarification with no stores."""
        response = engine.get_clarification_response("navigate", [])
        assert "no" in response.lower()

    def test_format_store_list_single(self, engine):
        """Test formatting single store."""
        result = engine._format_store_list(["Demo Fashion"])
        assert result == "Demo Fashion"

    def test_format_store_list_two(self, engine):
        """Test formatting two stores."""
        result = engine._format_store_list(["Demo Fashion", "Urban Wear"])
        assert result == "Demo Fashion y Urban Wear"

    def test_format_store_list_multiple(self, engine):
        """Test formatting multiple stores."""
        result = engine._format_store_list(["Demo Fashion", "Urban Wear", "Coffee Point"])
        assert result == "Demo Fashion, Urban Wear y Coffee Point"


class TestSafeResponses:
    """Tests for safe responses."""

    def test_is_safe_intent_greeting(self):
        """Test greeting is safe."""
        assert is_safe_intent("greeting")

    def test_is_safe_intent_goodbye(self):
        """Test goodbye is safe."""
        assert is_safe_intent("goodbye")

    def test_is_safe_intent_help(self):
        """Test help is safe."""
        assert is_safe_intent("help")

    def test_is_safe_intent_navigate(self):
        """Test navigate is not safe (needs data)."""
        assert not is_safe_intent("navigate")

    def test_is_safe_intent_unknown(self):
        """Test unknown is not safe."""
        assert not is_safe_intent("unknown")

    def test_get_safe_response_greeting(self):
        """Test getting greeting response."""
        response = get_safe_response("greeting")
        assert response is not None
        assert "Sofía" in response

    def test_get_safe_response_goodbye(self):
        """Test getting goodbye response."""
        response = get_safe_response("goodbye")
        assert response is not None
        assert "luego" in response.lower()

    def test_get_safe_response_invalid(self):
        """Test getting response for invalid intent."""
        response = get_safe_response("invalid")
        assert response is None
