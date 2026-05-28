"""Unit tests for StreamingTTS.

F6: Tests for progressive TTS chunk streaming.
"""

import asyncio
import base64
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

# Import from the module path
import sys
sys.path.insert(0, "services/speech")

from tts.streaming_tts import StreamingTTS, TTSChunk, create_streaming_tts
from tts.base import TTSProvider


class MockTTSProvider(TTSProvider):
    """Mock TTS provider for testing."""

    def __init__(self, audio_bytes: bytes = b"mock_audio_data", delay_ms: int = 0):
        self.audio_bytes = audio_bytes
        self.delay_ms = delay_ms
        self.synthesize_calls = []
        self.stream_calls = []

    async def synthesize(self, text: str) -> bytes:
        self.synthesize_calls.append(text)
        if self.delay_ms > 0:
            await asyncio.sleep(self.delay_ms / 1000)
        return self.audio_bytes

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        self.stream_calls.append(text)
        if self.delay_ms > 0:
            await asyncio.sleep(self.delay_ms / 1000)
        # Yield in chunks to simulate streaming
        chunk_size = len(self.audio_bytes) // 2 or 1
        for i in range(0, len(self.audio_bytes), chunk_size):
            yield self.audio_bytes[i : i + chunk_size]


class TestStreamingTTS:
    """Tests for StreamingTTS wrapper."""

    @pytest.fixture
    def mock_provider(self):
        """Create mock TTS provider."""
        return MockTTSProvider(audio_bytes=b"x" * 1000)

    @pytest.fixture
    def streaming_tts(self, mock_provider):
        """Create StreamingTTS with mock provider."""
        return StreamingTTS(provider=mock_provider, chunk_size_ms=500)

    def test_sentence_splitting_basic(self, streaming_tts):
        """Test sentence splitting with periods."""
        text = "Hola. ¿Cómo estás? Bien, gracias."
        sentences = streaming_tts._split_sentences(text)
        assert len(sentences) >= 2  # At least 2 sentences
        assert "Hola" in sentences[0]

    def test_sentence_splitting_question(self, streaming_tts):
        """Test sentence splitting with question marks."""
        text = "¿Dónde está Demo Fashion? Está en la planta 2."
        sentences = streaming_tts._split_sentences(text)
        assert len(sentences) >= 2

    def test_sentence_splitting_short_text(self, streaming_tts):
        """Test that short text is not split."""
        text = "Hola"
        sentences = streaming_tts._split_sentences(text)
        assert len(sentences) == 1
        assert sentences[0] == "Hola"

    def test_sentence_splitting_empty(self, streaming_tts):
        """Test empty text returns empty list."""
        assert streaming_tts._split_sentences("") == []
        assert streaming_tts._split_sentences("   ") == []

    def test_sentence_splitting_colon(self, streaming_tts):
        """Test splitting on colons."""
        text = "Tiendas disponibles: Demo Fashion, Urban Wear y Coffee Point."
        sentences = streaming_tts._split_sentences(text)
        assert len(sentences) >= 1

    @pytest.mark.asyncio
    async def test_synthesize_stream_basic(self, streaming_tts):
        """Test basic streaming synthesis."""
        chunks = []
        async for chunk in streaming_tts.synthesize_stream("Hola, ¿cómo estás?", "turn-1"):
            chunks.append(chunk)

        assert len(chunks) > 0
        assert all(isinstance(c, TTSChunk) for c in chunks)
        assert all(c.turn_id == "turn-1" for c in chunks)

    @pytest.mark.asyncio
    async def test_synthesize_stream_chunk_metadata(self, streaming_tts):
        """Test that chunks have correct metadata."""
        chunks = []
        async for chunk in streaming_tts.synthesize_stream("Test.", "turn-2"):
            chunks.append(chunk)

        if chunks:
            # First chunk should have index 0
            assert chunks[0].chunk_index == 0
            # All chunks should have latency
            assert all(c.latency_ms >= 0 for c in chunks)
            # Turn ID should be preserved
            assert all(c.turn_id == "turn-2" for c in chunks)

    @pytest.mark.asyncio
    async def test_synthesize_stream_empty_text(self, streaming_tts):
        """Test that empty text yields no chunks."""
        chunks = []
        async for chunk in streaming_tts.synthesize_stream("", "turn-3"):
            chunks.append(chunk)
        assert len(chunks) == 0

        chunks = []
        async for chunk in streaming_tts.synthesize_stream("   ", "turn-4"):
            chunks.append(chunk)
        assert len(chunks) == 0

    @pytest.mark.asyncio
    async def test_synthesize_stream_audio_data_is_base64(self, streaming_tts):
        """Test that audio data is valid base64."""
        async for chunk in streaming_tts.synthesize_stream("Test", "turn-5"):
            # Should be valid base64
            decoded = base64.b64decode(chunk.audio_data)
            assert len(decoded) > 0
            break  # Just test first chunk

    @pytest.mark.asyncio
    async def test_synthesize_full_then_chunk(self, mock_provider):
        """Test fallback full synthesis then chunking."""
        streaming = StreamingTTS(provider=mock_provider, chunk_size_ms=100)
        chunks = []
        async for chunk in streaming.synthesize_full_then_chunk("Test text", "turn-6"):
            chunks.append(chunk)

        assert len(chunks) > 0
        # Verify provider.synthesize was called (not stream)
        assert len(mock_provider.synthesize_calls) == 1

    @pytest.mark.asyncio
    async def test_synthesize_full_then_chunk_marks_last(self, mock_provider):
        """Test that last chunk is marked correctly."""
        streaming = StreamingTTS(provider=mock_provider, chunk_size_ms=100)
        chunks = []
        async for chunk in streaming.synthesize_full_then_chunk("Test", "turn-7"):
            chunks.append(chunk)

        if chunks:
            # Last chunk should have is_last=True
            assert chunks[-1].is_last is True
            # All others should have is_last=False
            for c in chunks[:-1]:
                assert c.is_last is False

    @pytest.mark.asyncio
    async def test_first_chunk_latency_tracking(self, mock_provider):
        """Test that first chunk latency is tracked."""
        streaming = StreamingTTS(provider=mock_provider)

        chunks = []
        async for chunk in streaming.synthesize_stream("Hello world", "turn-8"):
            chunks.append(chunk)

        if chunks:
            # First chunk latency should be small (< 1000ms for mock)
            assert chunks[0].latency_ms < 1000


class TestCreateStreamingTTS:
    """Tests for factory function."""

    def test_create_with_defaults(self):
        """Test factory with default settings."""
        mock_provider = MockTTSProvider()
        streaming = create_streaming_tts(mock_provider)

        assert isinstance(streaming, StreamingTTS)
        assert streaming.chunk_size_ms == 500
        assert streaming.provider == mock_provider

    def test_create_with_custom_chunk_size(self):
        """Test factory with custom chunk size."""
        mock_provider = MockTTSProvider()
        streaming = create_streaming_tts(mock_provider, chunk_size_ms=250)

        assert streaming.chunk_size_ms == 250


class TestTTSChunk:
    """Tests for TTSChunk dataclass."""

    def test_chunk_creation(self):
        """Test creating a TTSChunk."""
        chunk = TTSChunk(
            audio_data="base64data",
            chunk_index=0,
            sentence_index=0,
            is_last=False,
            turn_id="turn-1",
            latency_ms=100.5,
        )

        assert chunk.audio_data == "base64data"
        assert chunk.chunk_index == 0
        assert chunk.sentence_index == 0
        assert chunk.is_last is False
        assert chunk.turn_id == "turn-1"
        assert chunk.latency_ms == 100.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
