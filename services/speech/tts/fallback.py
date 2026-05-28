"""Fallback wrapper for TTS providers."""

from __future__ import annotations

from typing import AsyncIterator

import structlog

from .base import TTSProvider

log = structlog.get_logger()


class FallbackTTSProvider(TTSProvider):
    """TTS provider that falls back to secondary on error."""

    def __init__(self, primary: TTSProvider, fallback: TTSProvider):
        """Initialize fallback TTS provider.

        Args:
            primary: Primary TTS provider (e.g., API-based)
            fallback: Fallback TTS provider (e.g., local)
        """
        self.primary = primary
        self.fallback = fallback

    async def synthesize(self, text: str) -> bytes:
        """Synthesize audio, falling back on error.

        Args:
            text: Text to synthesize

        Returns:
            Audio bytes from primary or fallback provider
        """
        try:
            return await self.primary.synthesize(text)
        except Exception as e:
            log.warning(
                "tts_primary_failed",
                error=str(e),
                fallback="local",
            )
            return await self.fallback.synthesize(text)

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """Stream audio synthesis, falling back on error.

        Args:
            text: Text to synthesize

        Yields:
            Audio chunks from primary or fallback provider
        """
        try:
            async for chunk in self.primary.synthesize_stream(text):
                yield chunk
        except Exception as e:
            log.warning(
                "tts_stream_primary_failed",
                error=str(e),
                fallback="local",
            )
            async for chunk in self.fallback.synthesize_stream(text):
                yield chunk
