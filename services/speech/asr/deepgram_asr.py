"""Deepgram ASR implementation."""

from __future__ import annotations

import time
from typing import Optional

import structlog
from deepgram import DeepgramClient, PrerecordedOptions

from .base import ASRProvider, TranscriptResult

log = structlog.get_logger()


class DeepgramASR(ASRProvider):
    """ASR using Deepgram API."""

    def __init__(
        self,
        api_key: str,
        language: str = "es",
        model: str = "nova-2",
    ):
        """Initialize Deepgram ASR.

        Args:
            api_key: Deepgram API key
            language: Language code (e.g., 'es' for Spanish)
            model: Deepgram model to use
        """
        self.client = DeepgramClient(api_key)
        self.language = language
        self.model = model

    async def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> TranscriptResult:
        """Transcribe audio using Deepgram.

        Args:
            audio_bytes: Raw PCM audio bytes (16-bit signed)
            sample_rate: Audio sample rate

        Returns:
            TranscriptResult with transcription
        """
        start_time = time.time()

        try:
            # Configure options
            options = PrerecordedOptions(
                model=self.model,
                language=self.language,
                smart_format=True,
                punctuate=True,
            )

            # Send to Deepgram
            source = {"buffer": audio_bytes, "mimetype": "audio/raw"}
            response = await self.client.listen.asyncrest.v("1").transcribe_file(
                source,
                options,
                timeout=30.0,
            )

            # Extract result
            result = response.results.channels[0].alternatives[0]
            text = result.transcript
            confidence = result.confidence

            duration_ms = int((time.time() - start_time) * 1000)

            log.info(
                "asr_transcribed",
                text_length=len(text),
                confidence=confidence,
                duration_ms=duration_ms,
            )

            return TranscriptResult(
                text=text,
                confidence=confidence,
                duration_ms=duration_ms,
                language=self.language,
            )

        except Exception as e:
            log.error("asr_error", error=str(e))
            raise
