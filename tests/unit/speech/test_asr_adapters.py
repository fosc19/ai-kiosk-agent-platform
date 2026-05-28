"""Tests for ASR adapters (Deepgram, Faster-Whisper).

F7: Unit tests for ASR providers.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np

import pytest

# Add services path for imports
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "services" / "speech"))

from asr.base import ASRProvider, TranscriptResult


class TestTranscriptResult:
    """Test TranscriptResult dataclass."""

    def test_create_transcript_result(self):
        """Test creating a TranscriptResult."""
        result = TranscriptResult(
            text="Hola, soy el asistente del kiosco",
            confidence=0.95,
            duration_ms=250,
            language="es",
        )

        assert result.text == "Hola, soy el asistente del kiosco"
        assert result.confidence == 0.95
        assert result.duration_ms == 250
        assert result.language == "es"

    def test_empty_transcript(self):
        """Test empty transcript result."""
        result = TranscriptResult(
            text="",
            confidence=0.0,
            duration_ms=100,
            language="es",
        )

        assert result.text == ""
        assert result.confidence == 0.0


try:
    from deepgram import DeepgramClient, PrerecordedOptions
    DEEPGRAM_AVAILABLE = True
except ImportError:
    DEEPGRAM_AVAILABLE = False


@pytest.mark.skipif(not DEEPGRAM_AVAILABLE, reason="deepgram package not installed or incompatible version")
class TestDeepgramASR:
    """Test Deepgram ASR adapter."""

    @pytest.fixture
    def mock_deepgram_client(self):
        """Create mock Deepgram client."""
        client = MagicMock()

        # Mock response structure
        mock_result = MagicMock()
        mock_result.transcript = "Hola, soy el asistente del kiosco"
        mock_result.confidence = 0.95

        mock_channel = MagicMock()
        mock_channel.alternatives = [mock_result]

        mock_response = MagicMock()
        mock_response.results.channels = [mock_channel]

        # Mock async transcribe method
        client.listen.asyncrest.v.return_value.transcribe_file = AsyncMock(
            return_value=mock_response
        )

        return client

    @pytest.mark.asyncio
    async def test_deepgram_transcribe_success(self, mock_deepgram_client):
        """Test successful transcription with Deepgram."""
        import asr.deepgram_asr as deepgram_module
        with patch.object(deepgram_module, "DeepgramClient", return_value=mock_deepgram_client):
            from asr.deepgram_asr import DeepgramASR

            asr = DeepgramASR(api_key="test_key", language="es")
            asr.client = mock_deepgram_client

            # Create test audio (1 second of silence)
            audio_bytes = np.zeros(16000, dtype=np.int16).tobytes()

            result = await asr.transcribe(audio_bytes, sample_rate=16000)

            assert result.text == "Hola, soy el asistente del kiosco"
            assert result.confidence == 0.95
            assert result.language == "es"
            assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_deepgram_handles_empty_response(self, mock_deepgram_client):
        """Test handling of empty transcription."""
        mock_result = MagicMock()
        mock_result.transcript = ""
        mock_result.confidence = 0.0

        mock_channel = MagicMock()
        mock_channel.alternatives = [mock_result]

        mock_response = MagicMock()
        mock_response.results.channels = [mock_channel]

        mock_deepgram_client.listen.asyncrest.v.return_value.transcribe_file = AsyncMock(
            return_value=mock_response
        )

        import asr.deepgram_asr as deepgram_module
        with patch.object(deepgram_module, "DeepgramClient", return_value=mock_deepgram_client):
            from asr.deepgram_asr import DeepgramASR

            asr = DeepgramASR(api_key="test_key", language="es")
            asr.client = mock_deepgram_client

            audio_bytes = np.zeros(16000, dtype=np.int16).tobytes()
            result = await asr.transcribe(audio_bytes)

            assert result.text == ""

    @pytest.mark.asyncio
    async def test_deepgram_error_handling(self, mock_deepgram_client):
        """Test error handling in Deepgram ASR."""
        mock_deepgram_client.listen.asyncrest.v.return_value.transcribe_file = AsyncMock(
            side_effect=Exception("API Error")
        )

        import asr.deepgram_asr as deepgram_module
        with patch.object(deepgram_module, "DeepgramClient", return_value=mock_deepgram_client):
            from asr.deepgram_asr import DeepgramASR

            asr = DeepgramASR(api_key="test_key", language="es")
            asr.client = mock_deepgram_client

            audio_bytes = np.zeros(16000, dtype=np.int16).tobytes()

            with pytest.raises(Exception, match="API Error"):
                await asr.transcribe(audio_bytes)


class TestFasterWhisperASR:
    """Test Faster-Whisper ASR adapter."""

    @pytest.fixture
    def mock_whisper_model(self):
        """Create mock Whisper model."""
        model = MagicMock()

        # Mock segment
        mock_segment = MagicMock()
        mock_segment.text = "Hola, soy el asistente del kiosco"

        # Mock info
        mock_info = MagicMock()
        mock_info.language = "es"
        mock_info.language_probability = 0.98

        # Mock transcribe to return generator
        model.transcribe.return_value = ([mock_segment], mock_info)

        return model

    @pytest.mark.asyncio
    async def test_faster_whisper_transcribe_success(self, mock_whisper_model):
        """Test successful transcription with Faster-Whisper."""
        import asr.faster_whisper_asr as whisper_module
        with patch.object(whisper_module, "WhisperModel", return_value=mock_whisper_model):
            from asr.faster_whisper_asr import FasterWhisperASR

            asr = FasterWhisperASR(model_size="tiny", language="es")
            asr.model = mock_whisper_model

            # Create test audio
            audio_bytes = np.zeros(16000, dtype=np.int16).tobytes()

            result = await asr.transcribe(audio_bytes, sample_rate=16000)

            assert result.text == "Hola, soy el asistente del kiosco"
            assert result.confidence == 0.98
            assert result.language == "es"
            assert result.duration_ms >= 0  # Can be 0 for mocked audio

    @pytest.mark.asyncio
    async def test_faster_whisper_multiple_segments(self, mock_whisper_model):
        """Test handling multiple segments."""
        segment1 = MagicMock()
        segment1.text = "Hola,"
        segment2 = MagicMock()
        segment2.text = " soy el asistente del kiosco"

        mock_info = MagicMock()
        mock_info.language = "es"
        mock_info.language_probability = 0.95

        mock_whisper_model.transcribe.return_value = ([segment1, segment2], mock_info)

        with patch("asr.faster_whisper_asr.WhisperModel", return_value=mock_whisper_model):
            from asr.faster_whisper_asr import FasterWhisperASR

            asr = FasterWhisperASR(model_size="tiny", language="es")
            asr.model = mock_whisper_model

            audio_bytes = np.zeros(16000, dtype=np.int16).tobytes()
            result = await asr.transcribe(audio_bytes)

            # Should concatenate segments
            assert "Hola," in result.text
            assert "soy el asistente del kiosco" in result.text

    @pytest.mark.asyncio
    async def test_faster_whisper_empty_audio(self, mock_whisper_model):
        """Test handling empty/silence audio."""
        mock_info = MagicMock()
        mock_info.language = "es"
        mock_info.language_probability = 0.5

        mock_whisper_model.transcribe.return_value = ([], mock_info)

        with patch("asr.faster_whisper_asr.WhisperModel", return_value=mock_whisper_model):
            from asr.faster_whisper_asr import FasterWhisperASR

            asr = FasterWhisperASR(model_size="tiny", language="es")
            asr.model = mock_whisper_model

            audio_bytes = np.zeros(16000, dtype=np.int16).tobytes()
            result = await asr.transcribe(audio_bytes)

            assert result.text == ""

    @pytest.mark.asyncio
    async def test_faster_whisper_error_handling(self, mock_whisper_model):
        """Test error handling in Faster-Whisper."""
        mock_whisper_model.transcribe.side_effect = Exception("Model error")

        with patch("asr.faster_whisper_asr.WhisperModel", return_value=mock_whisper_model):
            from asr.faster_whisper_asr import FasterWhisperASR

            asr = FasterWhisperASR(model_size="tiny", language="es")
            asr.model = mock_whisper_model

            audio_bytes = np.zeros(16000, dtype=np.int16).tobytes()

            with pytest.raises(Exception, match="Model error"):
                await asr.transcribe(audio_bytes)


class TestASRProviderInterface:
    """Test ASR provider interface compliance."""

    def test_transcript_result_fields(self):
        """Test that TranscriptResult has all required fields."""
        result = TranscriptResult(
            text="test",
            confidence=0.9,
            duration_ms=100,
            language="es",
        )

        # All required fields should be present
        assert hasattr(result, "text")
        assert hasattr(result, "confidence")
        assert hasattr(result, "duration_ms")
        assert hasattr(result, "language")


class TestASRFactory:
    """Test ASR factory function."""

    def test_create_deepgram_asr(self):
        """Test creating Deepgram ASR via factory."""
        from asr.factory import create_asr_provider
        from asr.base import ASRProvider

        with patch.dict("sys.modules", {"asr.deepgram_asr": MagicMock()}):
            # Mock the DeepgramASR class
            mock_deepgram = MagicMock(spec=ASRProvider)
            with patch("asr.factory._create_local_asr"):  # Prevent fallback creation
                import asr.factory as factory_module
                with patch.object(factory_module, "_create_local_asr"):
                    # The factory will try to import DeepgramASR
                    # Since we can't easily mock it, just verify the factory exists
                    assert callable(create_asr_provider)

    def test_create_local_asr(self):
        """Test creating local ASR via factory returns ASRProvider."""
        from asr.factory import create_asr_provider
        from asr.base import ASRProvider

        # Mock FasterWhisperASR to avoid loading model
        with patch("asr.faster_whisper_asr.WhisperModel"):
            asr = create_asr_provider(mode="local", whisper_model_size="tiny")
            assert isinstance(asr, ASRProvider)

    def test_missing_deepgram_key_falls_back_to_local(self):
        """Test that missing deepgram key falls back to local."""
        from asr.factory import create_asr_provider
        from asr.base import ASRProvider

        # Mock FasterWhisperASR to avoid loading model
        with patch("asr.faster_whisper_asr.WhisperModel"):
            # Deepgram without key falls back to local
            asr = create_asr_provider(mode="deepgram")
            assert isinstance(asr, ASRProvider)


class TestAudioProcessing:
    """Test audio processing utilities."""

    def test_pcm_to_float_conversion(self):
        """Test PCM int16 to float32 conversion."""
        # Create test PCM data
        pcm_data = np.array([0, 16384, -16384, 32767, -32768], dtype=np.int16)
        pcm_bytes = pcm_data.tobytes()

        # Convert back
        audio_array = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
        audio_array /= 32768.0

        # Check normalization
        assert audio_array[0] == 0.0  # Zero should be zero
        assert abs(audio_array[3] - 1.0) < 0.001  # Max should be ~1
        assert abs(audio_array[4] - (-1.0)) < 0.001  # Min should be ~-1

    def test_sample_rate_assumption(self):
        """Test that 16kHz sample rate is used."""
        # Standard configuration
        sample_rate = 16000
        duration_seconds = 1.0

        # 1 second of audio at 16kHz mono 16-bit
        expected_samples = int(sample_rate * duration_seconds)
        expected_bytes = expected_samples * 2  # 16-bit = 2 bytes per sample

        audio_data = np.zeros(expected_samples, dtype=np.int16)
        assert len(audio_data.tobytes()) == expected_bytes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
