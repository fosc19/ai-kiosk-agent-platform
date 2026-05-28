"""Base interface for ASR providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TranscriptResult:
    """Result from ASR transcription."""

    text: str
    confidence: float
    duration_ms: int
    language: str


class ASRProvider(ABC):
    """Abstract base class for ASR providers."""

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> TranscriptResult:
        """Transcribe audio to text.

        Args:
            audio_bytes: Raw PCM audio bytes (16-bit signed)
            sample_rate: Audio sample rate

        Returns:
            TranscriptResult with transcription
        """
        pass
