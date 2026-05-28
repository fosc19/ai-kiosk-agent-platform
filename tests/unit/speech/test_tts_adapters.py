"""Tests for TTS adapters (ElevenLabs, Piper).

F7: Unit tests for TTS providers.
"""

import asyncio
import io
import wave
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add services path for imports
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "services" / "speech"))

from tts.base import TTSProvider


class TestTTSProviderInterface:
    """Test TTS provider interface."""

    def test_tts_provider_is_abstract(self):
        """Test that TTSProvider is abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            TTSProvider()

    def test_tts_provider_requires_synthesize(self):
        """Test that TTSProvider requires synthesize method."""
        assert hasattr(TTSProvider, "synthesize")

    def test_tts_provider_requires_synthesize_stream(self):
        """Test that TTSProvider requires synthesize_stream method."""
        assert hasattr(TTSProvider, "synthesize_stream")


class TestElevenLabsTTS:
    """Test ElevenLabs TTS adapter."""

    @pytest.fixture
    def mock_elevenlabs_client(self):
        """Create mock ElevenLabs client."""
        client = MagicMock()

        # Mock audio generator
        async def mock_audio_generator():
            yield b"audio_chunk_1"
            yield b"audio_chunk_2"
            yield b"audio_chunk_3"

        client.text_to_speech.convert = AsyncMock(return_value=mock_audio_generator())

        return client

    @pytest.mark.asyncio
    async def test_elevenlabs_synthesize_success(self, mock_elevenlabs_client):
        """Test successful synthesis with ElevenLabs."""
        with patch("tts.elevenlabs_tts.AsyncElevenLabs", return_value=mock_elevenlabs_client):
            from tts.elevenlabs_tts import ElevenLabsTTS

            tts = ElevenLabsTTS(api_key="test_key")
            tts.client = mock_elevenlabs_client

            # Mock the convert to return an async generator
            async def mock_gen():
                yield b"audio_chunk_1"
                yield b"audio_chunk_2"

            mock_elevenlabs_client.text_to_speech.convert = AsyncMock(return_value=mock_gen())

            result = await tts.synthesize("Hola, soy el asistente del kiosco")

            assert result == b"audio_chunk_1audio_chunk_2"

    @pytest.mark.asyncio
    async def test_elevenlabs_synthesize_stream(self, mock_elevenlabs_client):
        """Test streaming synthesis with ElevenLabs."""
        with patch("tts.elevenlabs_tts.AsyncElevenLabs", return_value=mock_elevenlabs_client):
            from tts.elevenlabs_tts import ElevenLabsTTS

            tts = ElevenLabsTTS(api_key="test_key")
            tts.client = mock_elevenlabs_client

            async def mock_gen():
                yield b"chunk1"
                yield b"chunk2"
                yield b"chunk3"

            mock_elevenlabs_client.text_to_speech.convert = AsyncMock(return_value=mock_gen())

            chunks = []
            async for chunk in tts.synthesize_stream("Hola"):
                chunks.append(chunk)

            assert len(chunks) == 3
            assert chunks[0] == b"chunk1"

    @pytest.mark.asyncio
    async def test_elevenlabs_error_handling(self, mock_elevenlabs_client):
        """Test error handling in ElevenLabs TTS."""
        with patch("tts.elevenlabs_tts.AsyncElevenLabs", return_value=mock_elevenlabs_client):
            from tts.elevenlabs_tts import ElevenLabsTTS

            tts = ElevenLabsTTS(api_key="test_key")
            tts.client = mock_elevenlabs_client

            mock_elevenlabs_client.text_to_speech.convert = AsyncMock(
                side_effect=Exception("API Error")
            )

            with pytest.raises(Exception, match="API Error"):
                await tts.synthesize("Test")

    def test_elevenlabs_default_voice(self):
        """Test that ElevenLabs uses default voice."""
        with patch("tts.elevenlabs_tts.AsyncElevenLabs"):
            from tts.elevenlabs_tts import ElevenLabsTTS

            tts = ElevenLabsTTS(api_key="test_key")

            # Should have a default voice_id
            assert tts.voice_id is not None
            assert len(tts.voice_id) > 0


class TestPiperTTS:
    """Test Piper TTS adapter."""

    @pytest.fixture
    def mock_piper_voice(self):
        """Create mock Piper voice."""
        voice = MagicMock()

        # Mock audio chunk
        mock_chunk = MagicMock()
        mock_chunk.audio_int16_bytes = b"\x00\x00" * 1000  # Silence

        # Mock config
        voice.config.sample_rate = 22050

        # Mock synthesize to return generator
        voice.synthesize.return_value = [mock_chunk]

        return voice

    @pytest.mark.asyncio
    async def test_piper_synthesize_success(self, mock_piper_voice):
        """Test successful synthesis with Piper."""
        # Mock piper module
        mock_piper_module = MagicMock()
        mock_piper_module.PiperVoice.load.return_value = mock_piper_voice

        with patch.dict("sys.modules", {"piper": mock_piper_module}):
            from tts.piper_tts import PiperTTS

            tts = PiperTTS.__new__(PiperTTS)
            tts.voice = mock_piper_voice
            tts._sample_rate = 22050
            tts.speaker_id = 0

            # Mock _wav_to_mp3 to return input
            with patch.object(tts, "_wav_to_mp3", return_value=b"mp3_audio"):
                result = await tts.synthesize("Hola")

            assert result == b"mp3_audio"

    @pytest.mark.asyncio
    async def test_piper_synthesize_stream(self, mock_piper_voice):
        """Test streaming synthesis with Piper."""
        mock_piper_module = MagicMock()
        mock_piper_module.PiperVoice.load.return_value = mock_piper_voice

        with patch.dict("sys.modules", {"piper": mock_piper_module}):
            from tts.piper_tts import PiperTTS

            tts = PiperTTS.__new__(PiperTTS)
            tts.voice = mock_piper_voice
            tts._sample_rate = 22050
            tts.speaker_id = 0

            # Mock synthesize to return small audio
            with patch.object(tts, "synthesize", new_callable=AsyncMock) as mock_synth:
                mock_synth.return_value = b"a" * 10000  # 10KB audio

                chunks = []
                async for chunk in tts.synthesize_stream("Hola"):
                    chunks.append(chunk)

                # Should have at least one chunk with the audio data
                assert len(chunks) >= 1
                total_bytes = sum(len(c) for c in chunks)
                assert total_bytes == 10000

    @pytest.mark.asyncio
    async def test_piper_error_handling(self, mock_piper_voice):
        """Test error handling in Piper TTS."""
        mock_piper_voice.synthesize.side_effect = Exception("Synthesis error")

        mock_piper_module = MagicMock()
        mock_piper_module.PiperVoice.load.return_value = mock_piper_voice

        with patch.dict("sys.modules", {"piper": mock_piper_module}):
            from tts.piper_tts import PiperTTS

            tts = PiperTTS.__new__(PiperTTS)
            tts.voice = mock_piper_voice
            tts._sample_rate = 22050
            tts.speaker_id = 0

            with pytest.raises(Exception, match="Synthesis error"):
                await tts.synthesize("Test")

    def test_piper_wav_to_mp3_fallback(self, mock_piper_voice):
        """Test WAV to MP3 conversion fallback."""
        mock_piper_module = MagicMock()
        mock_piper_module.PiperVoice.load.return_value = mock_piper_voice

        with patch.dict("sys.modules", {"piper": mock_piper_module}):
            from tts.piper_tts import PiperTTS

            tts = PiperTTS.__new__(PiperTTS)
            tts.voice = mock_piper_voice
            tts._sample_rate = 22050
            tts.speaker_id = 0

            # Create minimal valid WAV
            wav_io = io.BytesIO()
            with wave.open(wav_io, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(22050)
                wav_file.writeframes(b"\x00\x00" * 100)
            wav_bytes = wav_io.getvalue()

            # When pydub is not available, should return WAV
            with patch.dict("sys.modules", {"pydub": None}):
                result = tts._wav_to_mp3(wav_bytes)

            # Should return original WAV on error (pydub not available)
            assert len(result) > 0


class TestTTSCache:
    """Test TTS caching functionality."""

    @pytest.mark.asyncio
    async def test_cache_stores_audio(self):
        """Test that cache stores synthesized audio via CachedTTSProvider."""
        from tts.cache import CachedTTSProvider, TTSCacheConfig

        # Create mock provider
        mock_provider = MagicMock()
        mock_provider.synthesize = AsyncMock(return_value=b"fake_audio_data")

        config = TTSCacheConfig(cache_dir="/tmp/tts_cache_test", persist_to_disk=False)
        cache = CachedTTSProvider(provider=mock_provider, config=config)

        # First call should generate
        text = "Hola, soy el asistente del kiosco"
        result1 = await cache.synthesize(text)
        assert result1 == b"fake_audio_data"

        # Second call should hit cache (provider not called again)
        mock_provider.synthesize.reset_mock()
        result2 = await cache.synthesize(text)
        assert result2 == b"fake_audio_data"
        mock_provider.synthesize.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_returns_none_on_miss(self):
        """Test that cache miss calls provider."""
        from tts.cache import CachedTTSProvider, TTSCacheConfig

        mock_provider = MagicMock()
        mock_provider.synthesize = AsyncMock(return_value=b"new_audio")

        config = TTSCacheConfig(cache_dir="/tmp/tts_cache_test", persist_to_disk=False)
        cache = CachedTTSProvider(provider=mock_provider, config=config)

        result = await cache.synthesize("nonexistent text")
        assert result == b"new_audio"
        mock_provider.synthesize.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_key_normalization(self):
        """Test that cache normalizes text for keys."""
        from tts.cache import CachedTTSProvider, TTSCacheConfig

        mock_provider = MagicMock()
        mock_provider.synthesize = AsyncMock(return_value=b"audio1")

        config = TTSCacheConfig(cache_dir="/tmp/tts_cache_test", persist_to_disk=False)
        cache = CachedTTSProvider(provider=mock_provider, config=config)

        # Cache key is based on normalized (lowercased) text
        text1 = "Hola soy el asistente del kiosco"
        await cache.synthesize(text1)

        # Same text with different case should hit cache
        mock_provider.synthesize.reset_mock()
        text2 = "hola soy el asistente del kiosco"
        await cache.synthesize(text2)
        mock_provider.synthesize.assert_not_called()


class TestTTSFactory:
    """Test TTS factory function."""

    def test_create_elevenlabs_tts(self):
        """Test creating ElevenLabs TTS via factory."""
        with patch("tts.elevenlabs_tts.ElevenLabsTTS") as mock_class:
            from tts.factory import create_tts_provider

            tts = create_tts_provider(mode="elevenlabs", elevenlabs_api_key="test_key")

            mock_class.assert_called_once()

    def test_create_local_tts(self):
        """Test creating local (Piper) TTS via factory."""
        with patch("tts.piper_tts.PiperTTS") as mock_class:
            from tts.factory import create_tts_provider

            tts = create_tts_provider(mode="local", piper_model_path="/path/to/model.onnx")

            mock_class.assert_called_once()

    def test_invalid_mode_returns_dummy(self):
        """Test that missing config returns dummy TTS."""
        from tts.factory import create_tts_provider

        # Without piper_model_path, returns dummy
        tts = create_tts_provider(mode="local")
        # Dummy TTS is returned (no error raised)
        assert tts is not None


class TestStreamingTTS:
    """Test streaming TTS functionality."""

    @pytest.mark.asyncio
    async def test_streaming_yields_chunks(self):
        """Test that streaming yields audio chunks."""
        from tts.streaming_tts import StreamingTTS

        # Create mock TTS provider
        mock_provider = MagicMock()

        async def mock_stream(text):
            for i in range(3):
                yield f"chunk_{i}".encode()

        mock_provider.synthesize_stream = mock_stream

        manager = StreamingTTS(provider=mock_provider)

        chunks = []
        async for chunk in manager.synthesize_stream("Hola"):
            chunks.append(chunk)

        assert len(chunks) == 3

    @pytest.mark.asyncio
    async def test_streaming_handles_empty_text(self):
        """Test streaming with empty text."""
        from tts.streaming_tts import StreamingTTS

        mock_provider = MagicMock()

        async def mock_stream(text):
            if not text:
                return
            yield b"chunk"

        mock_provider.synthesize_stream = mock_stream

        manager = StreamingTTS(provider=mock_provider)

        chunks = []
        async for chunk in manager.synthesize_stream(""):
            chunks.append(chunk)

        assert len(chunks) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
