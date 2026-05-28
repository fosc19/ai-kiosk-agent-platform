"""Tests for FallbackASRProvider - F6 error resilience."""

import pytest
from unittest.mock import AsyncMock, MagicMock

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "services" / "speech"))

from asr.fallback import FallbackASRProvider
from asr.base import ASRProvider, TranscriptResult


class MockASRProvider(ASRProvider):
    """Mock ASR provider for testing."""

    def __init__(self, transcript: str = "test transcript", should_fail: bool = False):
        self.transcript = transcript
        self.should_fail = should_fail
        self.transcribe_called = False

    async def transcribe(
        self, audio_bytes: bytes, sample_rate: int = 16000
    ) -> TranscriptResult:
        self.transcribe_called = True
        if self.should_fail:
            raise Exception("ASR service unavailable")
        return TranscriptResult(
            text=self.transcript,
            confidence=0.95,
            language="es",
            duration_ms=100,
        )


class TestFallbackASRProvider:
    """Tests for FallbackASRProvider."""

    @pytest.fixture
    def audio_bytes(self) -> bytes:
        """Sample audio bytes for testing."""
        return b"\x00" * 16000  # 1 second of silence

    # === Basic Fallback Behavior ===

    @pytest.mark.asyncio
    async def test_uses_primary_when_successful(self, audio_bytes):
        """Test that primary provider is used when successful."""
        primary = MockASRProvider(transcript="primary result")
        fallback = MockASRProvider(transcript="fallback result")

        provider = FallbackASRProvider(primary=primary, fallback=fallback)
        result = await provider.transcribe(audio_bytes)

        assert result.text == "primary result"
        assert primary.transcribe_called
        assert not fallback.transcribe_called

    @pytest.mark.asyncio
    async def test_uses_fallback_when_primary_fails(self, audio_bytes):
        """Test that fallback is used when primary fails."""
        primary = MockASRProvider(should_fail=True)
        fallback = MockASRProvider(transcript="fallback result")

        provider = FallbackASRProvider(primary=primary, fallback=fallback)
        result = await provider.transcribe(audio_bytes)

        assert result.text == "fallback result"
        assert primary.transcribe_called
        assert fallback.transcribe_called

    @pytest.mark.asyncio
    async def test_fallback_failure_propagates(self, audio_bytes):
        """Test that if both fail, exception is propagated."""
        primary = MockASRProvider(should_fail=True)
        fallback = MockASRProvider(should_fail=True)

        provider = FallbackASRProvider(primary=primary, fallback=fallback)

        with pytest.raises(Exception, match="ASR service unavailable"):
            await provider.transcribe(audio_bytes)

    # === Sample Rate Handling ===

    @pytest.mark.asyncio
    async def test_sample_rate_passed_to_primary(self, audio_bytes):
        """Test that sample rate is passed to primary provider."""
        primary = AsyncMock()
        primary.transcribe = AsyncMock(
            return_value=TranscriptResult(
                text="test", confidence=0.9, language="es", duration_ms=50
            )
        )
        fallback = MockASRProvider()

        provider = FallbackASRProvider(primary=primary, fallback=fallback)
        await provider.transcribe(audio_bytes, sample_rate=44100)

        primary.transcribe.assert_called_once_with(audio_bytes, 44100)

    @pytest.mark.asyncio
    async def test_sample_rate_passed_to_fallback(self, audio_bytes):
        """Test that sample rate is passed to fallback on primary failure."""
        primary = MockASRProvider(should_fail=True)
        fallback = AsyncMock()
        fallback.transcribe = AsyncMock(
            return_value=TranscriptResult(
                text="fallback", confidence=0.8, language="es", duration_ms=150
            )
        )

        provider = FallbackASRProvider(primary=primary, fallback=fallback)
        await provider.transcribe(audio_bytes, sample_rate=8000)

        fallback.transcribe.assert_called_once_with(audio_bytes, 8000)

    # === Result Properties ===

    @pytest.mark.asyncio
    async def test_result_confidence_from_primary(self, audio_bytes):
        """Test that confidence comes from the actual provider used."""
        primary = MockASRProvider(transcript="primary")
        fallback = MockASRProvider(transcript="fallback")

        provider = FallbackASRProvider(primary=primary, fallback=fallback)
        result = await provider.transcribe(audio_bytes)

        assert result.confidence == 0.95  # From MockASRProvider

    @pytest.mark.asyncio
    async def test_result_duration_from_fallback(self, audio_bytes):
        """Test that duration reflects the actual provider used."""
        primary = MockASRProvider(should_fail=True)

        # Create a fallback with measurable duration
        fallback = AsyncMock()
        fallback.transcribe = AsyncMock(
            return_value=TranscriptResult(
                text="fallback",
                confidence=0.8,
                language="es",
                duration_ms=250,  # Higher duration for fallback
            )
        )

        provider = FallbackASRProvider(primary=primary, fallback=fallback)
        result = await provider.transcribe(audio_bytes)

        assert result.duration_ms == 250

    # === Error Types ===

    @pytest.mark.asyncio
    async def test_handles_timeout_error(self, audio_bytes):
        """Test fallback on timeout error."""
        primary = AsyncMock()
        primary.transcribe = AsyncMock(side_effect=TimeoutError("Connection timed out"))
        fallback = MockASRProvider(transcript="fallback after timeout")

        provider = FallbackASRProvider(primary=primary, fallback=fallback)
        result = await provider.transcribe(audio_bytes)

        assert result.text == "fallback after timeout"

    @pytest.mark.asyncio
    async def test_handles_connection_error(self, audio_bytes):
        """Test fallback on connection error."""
        primary = AsyncMock()
        primary.transcribe = AsyncMock(
            side_effect=ConnectionError("Cannot connect to API")
        )
        fallback = MockASRProvider(transcript="fallback after connection error")

        provider = FallbackASRProvider(primary=primary, fallback=fallback)
        result = await provider.transcribe(audio_bytes)

        assert result.text == "fallback after connection error"

    @pytest.mark.asyncio
    async def test_handles_value_error(self, audio_bytes):
        """Test fallback on value error (e.g., invalid audio)."""
        primary = AsyncMock()
        primary.transcribe = AsyncMock(
            side_effect=ValueError("Invalid audio format")
        )
        fallback = MockASRProvider(transcript="fallback after value error")

        provider = FallbackASRProvider(primary=primary, fallback=fallback)
        result = await provider.transcribe(audio_bytes)

        assert result.text == "fallback after value error"

    # === F6 Integration Scenarios ===

    @pytest.mark.asyncio
    async def test_deepgram_to_whisper_fallback_scenario(self, audio_bytes):
        """Test realistic Deepgram -> Whisper fallback scenario.

        F6: API-based ASR (Deepgram) should fall back to local (Whisper)
        when API is unavailable.
        """
        # Simulate Deepgram API failure
        deepgram_mock = AsyncMock()
        deepgram_mock.transcribe = AsyncMock(
            side_effect=Exception("Deepgram API rate limit exceeded")
        )

        # Simulate local Whisper working
        whisper_mock = AsyncMock()
        whisper_mock.transcribe = AsyncMock(
            return_value=TranscriptResult(
                text="hola qué tal",
                confidence=0.88,
                language="es",
                duration_ms=800,  # Slower but works
            )
        )

        provider = FallbackASRProvider(primary=deepgram_mock, fallback=whisper_mock)
        result = await provider.transcribe(audio_bytes)

        assert result.text == "hola qué tal"
        assert result.confidence == 0.88
        deepgram_mock.transcribe.assert_called_once()
        whisper_mock.transcribe.assert_called_once()


class TestTranscriptResult:
    """Tests for TranscriptResult dataclass."""

    def test_default_values(self):
        """Test TranscriptResult with required values only."""
        result = TranscriptResult(
            text="test",
            confidence=0.9,
            language="es",
            duration_ms=100,
        )
        assert result.text == "test"
        assert result.confidence == 0.9
        assert result.language == "es"
        assert result.duration_ms == 100

    def test_empty_text(self):
        """Test TranscriptResult with empty text."""
        result = TranscriptResult(
            text="",
            confidence=0.0,
            language="es",
            duration_ms=50,
        )
        assert result.text == ""
        assert result.confidence == 0.0
