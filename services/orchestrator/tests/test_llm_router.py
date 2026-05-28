"""Tests for LLM-only router module (F6)."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from llm_router import LLMIntentClassifier, Intent, ClassificationResult
from llm_adapter import MockLLMAdapter, LLMClassification
from policies import PolicyEngine
from conversation_memory import ConversationContext, TurnRecord


class TestLLMIntentClassifier:
    """Tests for LLMIntentClassifier."""

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM adapter."""
        return MockLLMAdapter()

    @pytest.fixture
    def policy_engine(self):
        """Create policy engine."""
        return PolicyEngine(
            catalog_store_ids={"demo_fashion", "urban_wear", "coffee_point"},
            catalog_store_names={"Demo Fashion", "Urban Wear", "Coffee Point"},
        )

    @pytest.fixture
    def classifier(self, mock_llm, policy_engine):
        """Create LLM classifier."""
        return LLMIntentClassifier(
            llm_adapter=mock_llm,
            policy_engine=policy_engine,
        )

    @pytest.fixture
    def context_with_demo_fashion(self):
        """Create context with Demo Fashion as current store."""
        return ConversationContext(
            session_id="test",
            current_store_id="demo_fashion",
            current_store_name="Demo Fashion",
            last_intent="store_info",
        )

    @pytest.fixture
    def context_after_navigate(self):
        """Create context after navigation."""
        return ConversationContext(
            session_id="test",
            current_store_id="urban_wear",
            current_store_name="Urban Wear",
            last_intent="navigate",
        )

    # === Basic Classification ===

    @pytest.mark.asyncio
    async def test_classify_greeting(self, classifier):
        """Test greeting classification."""
        result = await classifier.classify("hola buenos días", ["Demo Fashion"])
        assert result.intent == Intent.GREETING
        assert result.source == "llm"

    @pytest.mark.asyncio
    async def test_classify_goodbye(self, classifier):
        """Test goodbye classification."""
        result = await classifier.classify("adiós hasta luego", ["Demo Fashion"])
        assert result.intent == Intent.GOODBYE

    @pytest.mark.asyncio
    async def test_classify_list_stores(self, classifier):
        """Test list stores classification."""
        result = await classifier.classify("qué tiendas hay", ["Demo Fashion"])
        assert result.intent == Intent.LIST_STORES

    @pytest.mark.asyncio
    async def test_classify_navigate_with_store(self, classifier):
        """Test navigation with known store."""
        result = await classifier.classify("dónde está Demo Fashion", ["Demo Fashion", "Urban Wear"])
        assert result.intent == Intent.NAVIGATE
        assert result.store_query == "Demo Fashion"

    @pytest.mark.asyncio
    async def test_classify_store_info(self, classifier):
        """Test store info classification."""
        result = await classifier.classify("información de Urban Wear", ["Demo Fashion", "Urban Wear"])
        assert result.intent == Intent.STORE_INFO
        assert result.store_query == "Urban Wear"

    @pytest.mark.asyncio
    async def test_classify_empty_text(self, classifier):
        """Test empty text."""
        result = await classifier.classify("", ["Demo Fashion"])
        assert result.intent == Intent.UNKNOWN
        assert result.confidence == 0.0
        assert result.source == "empty"

    # === Context-Aware Classification (F6) ===

    @pytest.mark.asyncio
    async def test_affirmative_after_store_info(self, classifier, context_with_demo_fashion):
        """Test 'sí' after store_info navigates to context store."""
        result = await classifier.classify(
            "sí",
            ["Demo Fashion", "Urban Wear"],
            context=context_with_demo_fashion,
        )
        assert result.intent == Intent.NAVIGATE
        assert result.store_query == "Demo Fashion"

    @pytest.mark.asyncio
    async def test_affirmative_vale(self, classifier, context_with_demo_fashion):
        """Test 'vale' as affirmative."""
        result = await classifier.classify(
            "vale",
            ["Demo Fashion", "Urban Wear"],
            context=context_with_demo_fashion,
        )
        assert result.intent == Intent.NAVIGATE
        assert result.store_query == "Demo Fashion"

    @pytest.mark.asyncio
    async def test_affirmative_ok(self, classifier, context_with_demo_fashion):
        """Test 'ok' as affirmative."""
        result = await classifier.classify(
            "ok",
            ["Demo Fashion", "Urban Wear"],
            context=context_with_demo_fashion,
        )
        assert result.intent == Intent.NAVIGATE

    # === Reference Resolution via Context ===

    @pytest.mark.asyncio
    async def test_location_reference_ahi(self, classifier, context_with_demo_fashion):
        """Test 'ahí' resolves to context store."""
        result = await classifier.classify(
            "llévame ahí",
            ["Demo Fashion", "Urban Wear"],
            context=context_with_demo_fashion,
        )
        assert result.intent == Intent.NAVIGATE
        assert result.store_query == "Demo Fashion"

    @pytest.mark.asyncio
    async def test_location_reference_alli(self, classifier, context_after_navigate):
        """Test 'allí' resolves to context store."""
        result = await classifier.classify(
            "quiero ir allí",
            ["Demo Fashion", "Urban Wear"],
            context=context_after_navigate,
        )
        assert result.intent == Intent.NAVIGATE
        assert result.store_query == "Urban Wear"

    @pytest.mark.asyncio
    async def test_possessive_reference_su_horario(self, classifier, context_with_demo_fashion):
        """Test 'su horario' resolves to context store."""
        result = await classifier.classify(
            "cuál es su horario",
            ["Demo Fashion", "Urban Wear"],
            context=context_with_demo_fashion,
        )
        assert result.intent == Intent.STORE_INFO
        assert result.store_query == "Demo Fashion"

    # === Multilingual (MockLLMAdapter has basic support) ===

    @pytest.mark.asyncio
    async def test_catalan_greeting(self, classifier):
        """Test Catalan greeting."""
        result = await classifier.classify("bon dia", ["Demo Fashion"])
        assert result.intent == Intent.GREETING

    @pytest.mark.asyncio
    async def test_english_greeting(self, classifier):
        """Test English greeting."""
        result = await classifier.classify("hello", ["Demo Fashion"])
        assert result.intent == Intent.GREETING

    @pytest.mark.asyncio
    async def test_english_stores_query(self, classifier):
        """Test English stores query."""
        result = await classifier.classify("what stores are there", ["Demo Fashion"])
        assert result.intent == Intent.LIST_STORES

    # === Without Context ===

    @pytest.mark.asyncio
    async def test_no_context_direct_query(self, classifier):
        """Test direct query without context."""
        result = await classifier.classify(
            "dónde está Urban Wear",
            ["Demo Fashion", "Urban Wear"],
            context=None,
        )
        assert result.intent == Intent.NAVIGATE
        assert result.store_query == "Urban Wear"


class TestClassificationResult:
    """Tests for ClassificationResult dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = ClassificationResult(intent=Intent.GREETING)
        assert result.intent == Intent.GREETING
        assert result.store_query is None
        assert result.confidence == 1.0
        assert result.source == "llm"
        assert result.latency_ms == 0.0
        assert result.reasoning is None

    def test_with_all_values(self):
        """Test with all values."""
        result = ClassificationResult(
            intent=Intent.NAVIGATE,
            store_query="Demo Fashion",
            confidence=0.9,
            source="llm",
            latency_ms=150.0,
            reasoning="User wants to navigate to Demo Fashion",
        )
        assert result.intent == Intent.NAVIGATE
        assert result.store_query == "Demo Fashion"
        assert result.confidence == 0.9
        assert result.source == "llm"
        assert result.latency_ms == 150.0
        assert result.reasoning == "User wants to navigate to Demo Fashion"


class TestIntent:
    """Tests for Intent enum."""

    def test_all_intents_exist(self):
        """Test all expected intents exist."""
        assert Intent.GREETING
        assert Intent.GOODBYE
        assert Intent.LIST_STORES
        assert Intent.STORE_INFO
        assert Intent.NAVIGATE
        assert Intent.HELP
        assert Intent.CLARIFY
        assert Intent.UNKNOWN

    def test_intent_values(self):
        """Test intent values."""
        assert Intent.GREETING.value == "greeting"
        assert Intent.CLARIFY.value == "clarify"
        assert Intent.NAVIGATE.value == "navigate"
