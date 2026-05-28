"""Base interface for TTS providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator


class TTSProvider(ABC):
    """Abstract base class for TTS providers."""

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Generate audio from text.

        Args:
            text: Text to synthesize

        Returns:
            Audio bytes (MP3 format)
        """
        pass

    @abstractmethod
    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """Generate audio from text in streaming chunks.

        Args:
            text: Text to synthesize

        Yields:
            Audio chunk bytes (MP3 format)
        """
        pass
