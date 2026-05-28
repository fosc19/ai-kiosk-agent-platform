"""Fallback wrapper for ASR providers."""

from __future__ import annotations

import structlog

from .base import ASRProvider, TranscriptResult

log = structlog.get_logger()


class FallbackASRProvider(ASRProvider):
    """ASR provider that falls back to secondary on error."""

    def __init__(self, primary: ASRProvider, fallback: ASRProvider):
        """Initialize fallback ASR provider.

        Args:
            primary: Primary ASR provider (e.g., API-based)
            fallback: Fallback ASR provider (e.g., local)
        """
        self.primary = primary
        self.fallback = fallback

    async def transcribe(
        self, audio_bytes: bytes, sample_rate: int = 16000
    ) -> TranscriptResult:
        """Transcribe audio, falling back on error.

        Args:
            audio_bytes: Raw PCM audio bytes
            sample_rate: Audio sample rate

        Returns:
            TranscriptResult from primary or fallback provider
        """
        try:
            return await self.primary.transcribe(audio_bytes, sample_rate)
        except Exception as e:
            log.warning(
                "asr_primary_failed",
                error=str(e),
                fallback="local",
            )
            return await self.fallback.transcribe(audio_bytes, sample_rate)
