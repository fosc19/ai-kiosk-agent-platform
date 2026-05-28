"""Tests for LLM adapter module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from llm_adapter import (
    MockLLMAdapter,
    OllamaLLMAdapter,
    LLMClassification,
    LLMResponse,
    create_llm_adapter,
)


class TestMockLLMAdapter:
    """Tests for MockLLMAdapter."""

    @pytest.fixture
    def adapter(self):
        return MockLLMAdapter()

    @pytest.mark.asyncio
    async def test_classify_greeting(self, adapter):
        """Test greeting classification."""
        result = await adapter.classify_intent("hola buenos días", ["Demo Fashion", "Urban Wear"])
        assert result.intent == "greeting"

    @pytest.mark.asyncio
    async def test_classify_goodbye(self, adapter):
        """Test goodbye classification."""
        result = await adapter.classify_intent("adiós hasta luego", ["Demo Fashion"])
        assert result.intent == "goodbye"

    @pytest.mark.asyncio
    async def test_classify_list_stores(self, adapter):
        """Test list stores classification."""
        result = await adapter.classify_intent("qué tiendas hay", ["Demo Fashion", "Urban Wear"])
        assert result.intent == "list_stores"

    @pytest.mark.asyncio
    async def test_classify_navigate_with_store(self, adapter):
        """Test navigation classification with store extraction."""
        result = await adapter.classify_intent("dónde está Demo Fashion", ["Demo Fashion", "Urban Wear"])
        assert result.intent == "navigate"
        assert result.store_query == "Demo Fashion"

    @pytest.mark.asyncio
    async def test_classify_navigate_without_store(self, adapter):
        """Test navigation classification without store."""
        result = await adapter.classify_intent("dónde está la tienda", ["Demo Fashion", "Urban Wear"])
        assert result.intent == "navigate"
        assert result.store_query is None

    @pytest.mark.asyncio
    async def test_classify_store_info(self, adapter):
        """Test store info classification."""
        result = await adapter.classify_intent("información de Demo Fashion", ["Demo Fashion", "Urban Wear"])
        assert result.intent == "store_info"
        assert result.store_query == "Demo Fashion"

    @pytest.mark.asyncio
    async def test_classify_unknown(self, adapter):
        """Test unknown classification."""
        result = await adapter.classify_intent("xyz abc 123", ["Demo Fashion"])
        assert result.intent == "unknown"
        assert result.confidence < 1.0

    @pytest.mark.asyncio
    async def test_generate_response(self, adapter):
        """Test response generation."""
        result = await adapter.generate_response("navigate", {"user_query": "test"})
        assert isinstance(result, LLMResponse)
        assert result.text

    @pytest.mark.asyncio
    async def test_close(self, adapter):
        """Test adapter close."""
        await adapter.close()  # Should not raise


class TestCreateLLMAdapter:
    """Tests for create_llm_adapter factory."""

    def test_create_mock_adapter(self):
        """Test creating mock adapter."""
        adapter = create_llm_adapter(mode="mock")
        assert isinstance(adapter, MockLLMAdapter)

    def test_create_anthropic_without_key_raises(self):
        """Test that anthropic mode requires API key."""
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY required"):
            create_llm_adapter(mode="anthropic")

    def test_create_unknown_mode_raises(self):
        """Test that unknown mode raises."""
        with pytest.raises(ValueError, match="Unknown LLM mode"):
            create_llm_adapter(mode="invalid")


class TestLLMClassification:
    """Tests for LLMClassification dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = LLMClassification(intent="greeting")
        assert result.intent == "greeting"
        assert result.store_query is None
        assert result.confidence == 0.9
        assert result.reasoning is None
        assert result.info_type is None

    def test_with_all_values(self):
        """Test with all values."""
        result = LLMClassification(
            intent="navigate",
            store_query="Demo Fashion",
            confidence=0.95,
            reasoning="User asked for directions",
        )
        assert result.intent == "navigate"
        assert result.store_query == "Demo Fashion"
        assert result.confidence == 0.95
        assert result.reasoning == "User asked for directions"

    def test_store_info_with_info_type(self):
        """Test store_info with info_type for specific queries."""
        result = LLMClassification(
            intent="store_info",
            store_query="Demo Fashion",
            confidence=0.95,
            info_type="hours",
            reasoning="User asked specifically for schedule",
        )
        assert result.intent == "store_info"
        assert result.store_query == "Demo Fashion"
        assert result.info_type == "hours"

    def test_list_stores_with_query_type(self):
        """Test list_stores with query_type for count queries."""
        result = LLMClassification(
            intent="list_stores",
            confidence=0.95,
            query_type="count",
            reasoning="User asked for number of stores",
        )
        assert result.intent == "list_stores"
        assert result.query_type == "count"

    def test_list_stores_with_filter(self):
        """Test list_stores with filter for open stores."""
        result = LLMClassification(
            intent="list_stores",
            confidence=0.95,
            filter="open_now",
            reasoning="User asked for open stores",
        )
        assert result.intent == "list_stores"
        assert result.filter == "open_now"


class TestOllamaLLMAdapter:
    """Tests for OllamaLLMAdapter."""

    @pytest.fixture
    def mock_openai_response(self):
        """Create a mock OpenAI response."""
        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = '{"intent": "navigate", "store_query": "Demo Fashion", "confidence": 0.95}'
        return response

    @pytest.mark.asyncio
    async def test_classify_intent_success(self, mock_openai_response):
        """Test successful intent classification with mocked Ollama."""
        with patch("openai.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_openai_response)
            mock_client_class.return_value = mock_client

            adapter = OllamaLLMAdapter(
                base_url="http://localhost:11434",
                model="qwen2.5:3b-instruct",
            )
            adapter.client = mock_client

            result = await adapter.classify_intent(
                "donde esta Demo Fashion",
                ["Demo Fashion", "Urban Wear"],
            )

            assert result.intent == "navigate"
            assert result.store_query == "Demo Fashion"
            assert result.confidence == 0.95

    @pytest.mark.asyncio
    async def test_classify_intent_json_error(self):
        """Test handling of invalid JSON response."""
        with patch("openai.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()

            # Return invalid JSON
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = "This is not JSON"
            mock_client.chat.completions.create = AsyncMock(return_value=response)
            mock_client_class.return_value = mock_client

            adapter = OllamaLLMAdapter()
            adapter.client = mock_client

            result = await adapter.classify_intent("test", ["Demo Fashion"])

            assert result.intent == "unknown"
            assert result.confidence == 0.3

    @pytest.mark.asyncio
    async def test_classify_intent_connection_error(self):
        """Test handling of connection errors."""
        with patch("openai.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=Exception("Connection refused")
            )
            mock_client_class.return_value = mock_client

            adapter = OllamaLLMAdapter()
            adapter.client = mock_client

            result = await adapter.classify_intent("test", ["Demo Fashion"])

            assert result.intent == "unknown"
            assert result.confidence == 0.3
            assert "Connection refused" in result.reasoning

    @pytest.mark.asyncio
    async def test_generate_response(self):
        """Test response generation."""
        with patch("openai.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()

            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = "Demo Fashion está en la planta 1."
            mock_client.chat.completions.create = AsyncMock(return_value=response)
            mock_client_class.return_value = mock_client

            adapter = OllamaLLMAdapter()
            adapter.client = mock_client

            result = await adapter.generate_response(
                "navigate",
                {"user_query": "donde esta Demo Fashion", "available_stores": ["Demo Fashion"]},
            )

            assert isinstance(result, LLMResponse)
            assert "Demo Fashion" in result.text

    @pytest.mark.asyncio
    async def test_close(self):
        """Test adapter close."""
        with patch("openai.AsyncOpenAI") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            adapter = OllamaLLMAdapter()
            adapter.client = mock_client

            await adapter.close()
            mock_client.close.assert_called_once()


class TestCreateOllamaAdapter:
    """Tests for create_llm_adapter with ollama mode."""

    def test_create_ollama_adapter_default_url(self):
        """Test creating ollama adapter with default URL."""
        with patch("openai.AsyncOpenAI"):
            adapter = create_llm_adapter(mode="ollama")
            assert isinstance(adapter, OllamaLLMAdapter)
            assert adapter.base_url == "http://localhost:11434"
            assert adapter.model == "qwen2.5:3b-instruct"

    def test_create_ollama_adapter_custom_url(self):
        """Test creating ollama adapter with custom URL."""
        with patch("openai.AsyncOpenAI"):
            adapter = create_llm_adapter(
                mode="ollama",
                api_key="http://192.168.1.100:11434",
            )
            assert isinstance(adapter, OllamaLLMAdapter)
            assert adapter.base_url == "http://192.168.1.100:11434"

    def test_create_ollama_adapter_custom_model(self):
        """Test creating ollama adapter with custom model."""
        with patch("openai.AsyncOpenAI"):
            adapter = create_llm_adapter(
                mode="ollama",
                model="qwen2.5:7b-instruct",
            )
            assert isinstance(adapter, OllamaLLMAdapter)
            assert adapter.model == "qwen2.5:7b-instruct"
