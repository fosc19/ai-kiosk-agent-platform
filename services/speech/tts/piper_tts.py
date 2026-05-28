"""Piper TTS implementation (local)."""

from __future__ import annotations

import io
import time
import wave
from typing import AsyncIterator, Optional

import structlog

from .base import TTSProvider

log = structlog.get_logger()

# Chunk size for streaming (bytes)
STREAM_CHUNK_SIZE = 4096


class PiperTTS(TTSProvider):
    """TTS using Piper (local, no API required)."""

    def __init__(
        self,
        model_path: str,
        config_path: Optional[str] = None,
        speaker_id: int = 0,
    ):
        """Initialize Piper TTS.

        Args:
            model_path: Path to the Piper .onnx model file
            config_path: Path to model config JSON (optional, auto-detected)
            speaker_id: Speaker ID for multi-speaker models
        """
        log.info("piper_loading", model_path=model_path, speaker_id=speaker_id)

        try:
            from piper import PiperVoice

            self.voice = PiperVoice.load(model_path, config_path=config_path)
            self.speaker_id = speaker_id
            self._sample_rate = self.voice.config.sample_rate

            log.info("piper_loaded", model_path=model_path, sample_rate=self._sample_rate)
        except ImportError:
            log.error("piper_import_error", hint="Install piper-tts package")
            raise
        except Exception as e:
            log.error("piper_load_error", error=str(e))
            raise

    def _sanitize_text(self, text: str) -> str:
        """Sanitize text for Piper TTS.

        Some Piper models have issues with certain punctuation marks.
        """
        # Replace exclamation marks (Piper es_ES model fails on these)
        text = text.replace("¡", "")
        text = text.replace("!", ".")
        # Replace inverted question mark
        text = text.replace("¿", "")
        return text

    async def synthesize(self, text: str) -> bytes:
        """Generate audio from text.

        Args:
            text: Text to synthesize

        Returns:
            Audio bytes (MP3 format)
        """
        start_time = time.time()

        # Sanitize text for Piper compatibility
        text = self._sanitize_text(text)

        try:
            # Collect audio from Piper generator
            # voice.synthesize() returns a generator of AudioChunk objects
            all_audio = b""
            for chunk in self.voice.synthesize(text):
                all_audio += chunk.audio_int16_bytes

            # Write to WAV format in memory
            wav_io = io.BytesIO()
            with wave.open(wav_io, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(self._sample_rate)
                wav_file.writeframes(all_audio)

            wav_bytes = wav_io.getvalue()

            # Convert WAV to MP3 using pydub
            mp3_bytes = self._wav_to_mp3(wav_bytes)

            duration_ms = int((time.time() - start_time) * 1000)

            log.info(
                "tts_synthesized_local",
                text_length=len(text),
                wav_bytes=len(wav_bytes),
                mp3_bytes=len(mp3_bytes),
                duration_ms=duration_ms,
            )

            return mp3_bytes

        except Exception as e:
            log.error("tts_local_error", error=str(e))
            raise

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """Generate audio from text in streaming chunks.

        Note: Piper generates complete audio, so we yield the entire audio
        as a single chunk. This is because MP3 chunks cannot be decoded
        individually - they require complete frames with headers.

        For true streaming, use ElevenLabs or another provider that
        supports real-time audio generation.

        Args:
            text: Text to synthesize

        Yields:
            Complete audio bytes (MP3 format) as a single chunk
        """
        start_time = time.time()

        try:
            # Generate complete audio
            audio_bytes = await self.synthesize(text)

            # Yield complete audio as single chunk (MP3 chunks aren't independently decodable)
            yield audio_bytes

            duration_ms = int((time.time() - start_time) * 1000)

            log.info(
                "tts_streamed_local",
                text_length=len(text),
                chunk_count=1,
                total_bytes=len(audio_bytes),
                duration_ms=duration_ms,
            )

        except Exception as e:
            log.error("tts_stream_local_error", error=str(e))
            raise

    def _wav_to_mp3(self, wav_bytes: bytes) -> bytes:
        """Convert WAV audio to MP3.

        Args:
            wav_bytes: WAV audio bytes

        Returns:
            MP3 audio bytes
        """
        try:
            from pydub import AudioSegment

            # Load WAV from bytes
            wav_io = io.BytesIO(wav_bytes)
            audio = AudioSegment.from_wav(wav_io)

            # Export to MP3
            mp3_io = io.BytesIO()
            audio.export(mp3_io, format="mp3", bitrate="128k")

            return mp3_io.getvalue()

        except ImportError:
            log.warning("pydub_not_available", returning="wav")
            return wav_bytes
        except Exception as e:
            log.warning("wav_to_mp3_failed", error=str(e), returning="wav")
            return wav_bytes
