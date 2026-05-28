"""ElevenLabs TTS implementation."""

from __future__ import annotations

import time
from typing import AsyncIterator

import structlog
from elevenlabs import AsyncElevenLabs

from .base import TTSProvider

log = structlog.get_logger()


class ElevenLabsTTS(TTSProvider):
    """TTS using ElevenLabs API."""

    def __init__(
        self,
        api_key: str,
        voice_id: str = "pNInz6obpgDQGcFmaJgB",  # Spanish female voice
        model_id: str = "eleven_multilingual_v2",
    ):
        """Initialize ElevenLabs TTS.

        Args:
            api_key: ElevenLabs API key
            voice_id: Voice ID to use
            model_id: Model ID to use
        """
        self.client = AsyncElevenLabs(api_key=api_key)
        self.voice_id = voice_id
        self.model_id = model_id

    async def synthesize(self, text: str) -> bytes:
        """Generate audio from text.

        Args:
            text: Text to synthesize

        Returns:
            Audio bytes (MP3 format)
        """
        start_time = time.time()

        try:
            audio = await self.client.text_to_speech.convert(
                voice_id=self.voice_id,
                text=text,
                model_id=self.model_id,
            )

            # Collect all chunks
            chunks = []
            async for chunk in audio:
                chunks.append(chunk)

            audio_bytes = b"".join(chunks)
            duration_ms = int((time.time() - start_time) * 1000)

            log.info(
                "tts_synthesized",
                text_length=len(text),
                audio_bytes=len(audio_bytes),
                duration_ms=duration_ms,
            )

            return audio_bytes

        except Exception as e:
            log.error("tts_error", error=str(e))
            raise

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """Generate audio from text in streaming chunks.

        Args:
            text: Text to synthesize

        Yields:
            Audio chunk bytes (MP3 format)
        """
        start_time = time.time()
        chunk_count = 0
        total_bytes = 0

        try:
            audio = await self.client.text_to_speech.convert(
                voice_id=self.voice_id,
                text=text,
                model_id=self.model_id,
            )

            async for chunk in audio:
                chunk_count += 1
                total_bytes += len(chunk)
                yield chunk

            duration_ms = int((time.time() - start_time) * 1000)

            log.info(
                "tts_streamed",
                text_length=len(text),
                chunk_count=chunk_count,
                total_bytes=total_bytes,
                duration_ms=duration_ms,
            )

        except Exception as e:
            log.error("tts_stream_error", error=str(e))
            raise
