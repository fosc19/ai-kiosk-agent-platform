"""Faster-Whisper ASR implementation (local)."""

from __future__ import annotations

import io
import time
from typing import Optional

import numpy as np
import structlog
from faster_whisper import WhisperModel

from .base import ASRProvider, TranscriptResult

log = structlog.get_logger()


class FasterWhisperASR(ASRProvider):
    """ASR using faster-whisper (local, no API required)."""

    def __init__(
        self,
        model_size: str = "small",
        language: str = "es",
        device: str = "auto",
        compute_type: str = "auto",
        prompt: str = "",
    ):
        """Initialize faster-whisper ASR.

        Args:
            model_size: Model size (tiny, base, small, medium, large-v2, large-v3)
            language: Language code (e.g., 'es' for Spanish)
            device: Device to use (auto, cpu, cuda)
            compute_type: Compute type (auto, int8, float16, float32)
            prompt: Initial prompt with vocabulary hints (e.g., store names)
        """
        log.info(
            "faster_whisper_loading",
            model_size=model_size,
            device=device,
            compute_type=compute_type,
        )

        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
        )
        self.language = language
        self.prompt = prompt if prompt else None

        log.info("faster_whisper_loaded", model_size=model_size, prompt=self.prompt)

    async def transcribe(
        self, audio_bytes: bytes, sample_rate: int = 16000
    ) -> TranscriptResult:
        """Transcribe audio using faster-whisper.

        Args:
            audio_bytes: Raw PCM audio bytes (16-bit signed, mono)
            sample_rate: Audio sample rate

        Returns:
            TranscriptResult with transcription
        """
        start_time = time.time()

        try:
            # Convert PCM bytes to float32 numpy array
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
            audio_array /= 32768.0  # Normalize to [-1, 1]

            # Resample if needed (faster-whisper expects 16kHz)
            if sample_rate != 16000:
                import torchaudio
                import torch

                audio_tensor = torch.from_numpy(audio_array).unsqueeze(0)
                resampler = torchaudio.transforms.Resample(sample_rate, 16000)
                audio_tensor = resampler(audio_tensor)
                audio_array = audio_tensor.squeeze(0).numpy()

            # Transcribe with faster-whisper
            segments, info = self.model.transcribe(
                audio_array,
                language=self.language,
                beam_size=5,
                vad_filter=True,
                initial_prompt=self.prompt,
            )

            # Collect all segments
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text)

            text = " ".join(text_parts).strip()
            duration_ms = int((time.time() - start_time) * 1000)

            log.info(
                "asr_transcribed_local",
                text_length=len(text),
                language=info.language,
                language_probability=info.language_probability,
                duration_ms=duration_ms,
            )

            return TranscriptResult(
                text=text,
                confidence=info.language_probability,
                duration_ms=duration_ms,
                language=info.language,
            )

        except Exception as e:
            log.error("asr_local_error", error=str(e))
            raise
