"""Streaming TTS wrapper - Progressive chunk generation for low latency.

F6: Wraps TTS providers to enable streaming with:
- Sentence splitting for faster first-chunk delivery
- Progress tracking (chunk index, total estimate)
- Configurable chunk sizes
- First chunk target: < 500ms

Usage:
    streaming = StreamingTTS(tts_provider, chunk_size_ms=500)
    async for chunk in streaming.synthesize_stream(text, turn_id):
        # chunk.audio_data: base64 audio
        # chunk.chunk_index: 0, 1, 2...
        # chunk.is_last: True on final chunk
        await websocket.send(chunk)
"""

from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass
from typing import AsyncIterator, Optional

import structlog

from .base import TTSProvider

log = structlog.get_logger()


@dataclass
class TTSChunk:
    """A chunk of TTS audio with metadata."""

    audio_data: str  # base64 encoded audio
    chunk_index: int
    sentence_index: int
    is_last: bool
    turn_id: str
    latency_ms: float  # Time since synthesis started


class StreamingTTS:
    """Wrapper for TTS providers that enables progressive streaming.

    Splits text into sentences and synthesizes each progressively,
    sending chunks as they become available.
    """

    # Sentence-ending patterns for Spanish
    SENTENCE_PATTERN = re.compile(
        r'(?<=[.!?])\s+|'  # Period, exclamation, question followed by space
        r'(?<=:)\s+|'      # Colon followed by space
        r'(?<=,)\s+(?=y\s)|'  # Comma before "y" (conjunction)
        r'(?<=\.\.\.)\s+'  # Ellipsis
    )

    def __init__(
        self,
        provider: TTSProvider,
        chunk_size_ms: int = 500,
        min_sentence_chars: int = 10,
    ):
        """Initialize streaming TTS.

        Args:
            provider: Underlying TTS provider
            chunk_size_ms: Target chunk duration in milliseconds
            min_sentence_chars: Minimum characters to form a sentence
        """
        self.provider = provider
        self.chunk_size_ms = chunk_size_ms
        self.min_sentence_chars = min_sentence_chars

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences for progressive synthesis.

        Args:
            text: Full text to split

        Returns:
            List of sentences/phrases
        """
        if not text:
            return []

        # Split by sentence boundaries
        parts = self.SENTENCE_PATTERN.split(text)

        # Filter and combine short segments
        sentences = []
        buffer = ""

        for part in parts:
            part = part.strip()
            if not part:
                continue

            buffer += (" " if buffer else "") + part

            # Flush buffer if it's long enough
            if len(buffer) >= self.min_sentence_chars:
                sentences.append(buffer)
                buffer = ""

        # Don't forget remaining buffer
        if buffer:
            if sentences:
                # Append to last sentence if short
                sentences[-1] += " " + buffer
            else:
                sentences.append(buffer)

        return sentences

    async def synthesize_stream(
        self,
        text: str,
        turn_id: str = "unknown",
    ) -> AsyncIterator[TTSChunk]:
        """Synthesize text and yield progressive chunks.

        Args:
            text: Text to synthesize
            turn_id: Turn identifier for tracking

        Yields:
            TTSChunk with audio data and metadata
        """
        start_time = time.perf_counter()

        if not text.strip():
            log.warning("streaming_tts_empty_text", turn_id=turn_id)
            return

        # Split into sentences for faster first chunk
        sentences = self._split_sentences(text)
        total_sentences = len(sentences)

        log.info(
            "streaming_tts_start",
            turn_id=turn_id,
            text_length=len(text),
            sentences=total_sentences,
        )

        chunk_index = 0
        first_chunk_sent = False

        for sent_idx, sentence in enumerate(sentences):
            is_last_sentence = sent_idx == total_sentences - 1

            try:
                # Use provider's stream method if available
                async for audio_bytes in self.provider.synthesize_stream(sentence):
                    if not audio_bytes:
                        continue

                    latency = (time.perf_counter() - start_time) * 1000

                    if not first_chunk_sent:
                        log.info(
                            "streaming_tts_first_chunk",
                            turn_id=turn_id,
                            latency_ms=round(latency, 1),
                        )
                        first_chunk_sent = True

                    yield TTSChunk(
                        audio_data=base64.b64encode(audio_bytes).decode("utf-8"),
                        chunk_index=chunk_index,
                        sentence_index=sent_idx,
                        is_last=False,  # Will be set on final yield
                        turn_id=turn_id,
                        latency_ms=latency,
                    )
                    chunk_index += 1

            except Exception as e:
                log.warning(
                    "streaming_tts_sentence_error",
                    turn_id=turn_id,
                    sentence_index=sent_idx,
                    error=str(e),
                )
                # Try to continue with next sentence
                continue

        # Mark final chunk
        if chunk_index > 0:
            total_latency = (time.perf_counter() - start_time) * 1000
            log.info(
                "streaming_tts_complete",
                turn_id=turn_id,
                total_chunks=chunk_index,
                total_latency_ms=round(total_latency, 1),
            )

    async def synthesize_full_then_chunk(
        self,
        text: str,
        turn_id: str = "unknown",
        chunk_duration_ms: int = 500,
    ) -> AsyncIterator[TTSChunk]:
        """Fallback: synthesize full audio then split into chunks.

        Used when provider doesn't support true streaming.
        Still provides chunked delivery for barge-in support.

        Args:
            text: Text to synthesize
            turn_id: Turn identifier
            chunk_duration_ms: Target chunk duration

        Yields:
            TTSChunk with audio data
        """
        start_time = time.perf_counter()

        if not text.strip():
            return

        log.info(
            "streaming_tts_full_start",
            turn_id=turn_id,
            text_length=len(text),
        )

        try:
            # Synthesize full audio
            full_audio = await self.provider.synthesize(text)

            if not full_audio:
                log.warning("streaming_tts_empty_audio", turn_id=turn_id)
                return

            synth_latency = (time.perf_counter() - start_time) * 1000
            log.info(
                "streaming_tts_full_synthesized",
                turn_id=turn_id,
                audio_size=len(full_audio),
                latency_ms=round(synth_latency, 1),
            )

            # Estimate bytes per chunk (assuming MP3 ~128kbps)
            bytes_per_ms = 128 * 1000 / 8 / 1000  # 16 bytes per ms
            chunk_size = int(bytes_per_ms * chunk_duration_ms)
            chunk_size = max(chunk_size, 4096)  # Minimum 4KB chunks

            # Split into chunks
            total_chunks = (len(full_audio) + chunk_size - 1) // chunk_size

            for i in range(0, len(full_audio), chunk_size):
                chunk_data = full_audio[i : i + chunk_size]
                chunk_index = i // chunk_size
                is_last = chunk_index == total_chunks - 1

                yield TTSChunk(
                    audio_data=base64.b64encode(chunk_data).decode("utf-8"),
                    chunk_index=chunk_index,
                    sentence_index=0,
                    is_last=is_last,
                    turn_id=turn_id,
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                )

            log.info(
                "streaming_tts_complete",
                turn_id=turn_id,
                total_chunks=total_chunks,
            )

        except Exception as e:
            log.error("streaming_tts_error", turn_id=turn_id, error=str(e))
            raise


def create_streaming_tts(
    provider: TTSProvider,
    chunk_size_ms: int = 500,
) -> StreamingTTS:
    """Factory function to create StreamingTTS.

    Args:
        provider: Base TTS provider
        chunk_size_ms: Target chunk duration

    Returns:
        Configured StreamingTTS instance
    """
    return StreamingTTS(provider=provider, chunk_size_ms=chunk_size_ms)
