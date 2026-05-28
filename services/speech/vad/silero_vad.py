"""Silero VAD wrapper for voice activity detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import structlog
import torch

log = structlog.get_logger()

SAMPLE_RATE = 16000
# Silero VAD requires exactly 512 samples for 16kHz (32ms windows)
SILERO_CHUNK_SIZE = 512


@dataclass
class VADResult:
    """Result from VAD processing."""

    is_speech: bool
    confidence: float
    speech_duration_ms: int
    silence_duration_ms: int
    end_of_speech: bool  # True when silence threshold reached after speech


class SileroVAD:
    """Voice Activity Detection using Silero VAD model."""

    def __init__(
        self,
        threshold: float = 0.5,
        min_speech_ms: int = 250,
        min_silence_ms: int = 500,
        sample_rate: int = SAMPLE_RATE,
    ):
        """Initialize Silero VAD.

        Args:
            threshold: Speech probability threshold (0-1)
            min_speech_ms: Minimum speech duration to consider valid
            min_silence_ms: Silence duration to trigger end of speech
            sample_rate: Audio sample rate (must be 16000 for Silero)
        """
        self.threshold = threshold
        self.min_speech_ms = min_speech_ms
        self.min_silence_ms = min_silence_ms
        self.sample_rate = sample_rate

        # Load Silero VAD model
        self.model, self.utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            onnx=False,
        )

        # State tracking
        self._speech_samples = 0
        self._silence_samples = 0
        self._has_speech = False
        self._leftover = np.array([], dtype=np.float32)  # Buffer for incomplete chunks

    def reset(self) -> None:
        """Reset VAD state for new utterance."""
        self._speech_samples = 0
        self._silence_samples = 0
        self._has_speech = False
        self._leftover = np.array([], dtype=np.float32)
        self.model.reset_states()

    def process_chunk(self, audio: np.ndarray) -> VADResult:
        """Process audio chunk and detect voice activity.

        Silero VAD requires exactly 512 samples at 16kHz. This method
        handles audio of any size by splitting into 512-sample windows
        and buffering any leftover samples for the next call.

        Args:
            audio: Audio samples as float32 numpy array, normalized to [-1, 1]

        Returns:
            VADResult with speech detection info (aggregated over all windows)
        """
        # Convert to float32 if needed
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Ensure audio is normalized
        if len(audio) > 0 and np.abs(audio).max() > 1.0:
            audio = audio / 32768.0  # Assume 16-bit PCM

        # Prepend any leftover from previous call
        if len(self._leftover) > 0:
            audio = np.concatenate([self._leftover, audio])
            self._leftover = np.array([], dtype=np.float32)

        # Process in 512-sample windows
        speech_probs = []
        processed_samples = 0

        for i in range(0, len(audio) - SILERO_CHUNK_SIZE + 1, SILERO_CHUNK_SIZE):
            chunk = audio[i : i + SILERO_CHUNK_SIZE]
            tensor = torch.from_numpy(chunk)

            # Get speech probability for this window
            prob = self.model(tensor, self.sample_rate).item()
            speech_probs.append(prob)
            processed_samples += SILERO_CHUNK_SIZE

        # Store leftover samples for next call
        if processed_samples < len(audio):
            self._leftover = audio[processed_samples:]

        # If no complete chunks were processed, return current state
        if not speech_probs:
            return VADResult(
                is_speech=False,
                confidence=0.0,
                speech_duration_ms=int(self._speech_samples / self.sample_rate * 1000),
                silence_duration_ms=int(self._silence_samples / self.sample_rate * 1000),
                end_of_speech=False,
            )

        # Aggregate results: use max probability and check if any window has speech
        max_prob = max(speech_probs)
        any_speech = max_prob >= self.threshold

        # Update counters based on aggregate result
        if any_speech:
            self._speech_samples += processed_samples
            self._silence_samples = 0
            self._has_speech = True
        else:
            self._silence_samples += processed_samples

        # Calculate durations in ms
        speech_duration_ms = int(self._speech_samples / self.sample_rate * 1000)
        silence_duration_ms = int(self._silence_samples / self.sample_rate * 1000)

        # Check for end of speech
        end_of_speech = (
            self._has_speech
            and speech_duration_ms >= self.min_speech_ms
            and silence_duration_ms >= self.min_silence_ms
        )

        return VADResult(
            is_speech=any_speech,
            confidence=max_prob,
            speech_duration_ms=speech_duration_ms,
            silence_duration_ms=silence_duration_ms,
            end_of_speech=end_of_speech,
        )

    @property
    def has_valid_speech(self) -> bool:
        """Check if we have accumulated enough speech."""
        speech_ms = int(self._speech_samples / self.sample_rate * 1000)
        return speech_ms >= self.min_speech_ms
