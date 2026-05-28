"""Barge-in Detector - Detect user interruptions during TTS playback.

F6: Enables natural conversation flow by detecting when the user
starts speaking while the assistant is playing audio (TTS).

The detector:
- Monitors audio energy during playback state
- Triggers barge-in when speech is detected for min_duration
- Avoids false positives from ambient noise
- Latency target: < 200ms from speech start to detection
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
import structlog

log = structlog.get_logger()

SAMPLE_RATE = 16000


@dataclass
class BargeInResult:
    """Result from barge-in detection."""

    detected: bool  # True if barge-in detected
    speech_duration_ms: int  # Duration of detected speech
    energy: float  # Current audio energy level
    latency_ms: float  # Time from first speech to detection


class BargeInDetector:
    """Detects speech during TTS playback for barge-in handling.

    Usage:
        detector = BargeInDetector(min_speech_duration_ms=150)

        # During TTS playback loop:
        for audio_chunk in microphone_stream:
            result = detector.process_chunk(audio_chunk, is_playing=True)
            if result.detected:
                # Stop TTS playback immediately
                stop_playback()
                break

        # Reset when playback stops
        detector.reset()
    """

    def __init__(
        self,
        min_speech_duration_ms: int = 150,
        energy_threshold: float = 0.02,
        sample_rate: int = SAMPLE_RATE,
    ):
        """Initialize barge-in detector.

        Args:
            min_speech_duration_ms: Minimum speech duration to trigger barge-in
                                   (prevents false positives from noise bursts)
            energy_threshold: RMS energy threshold to consider as speech
                             (tuned for post-AEC audio)
            sample_rate: Audio sample rate in Hz
        """
        self.min_speech_duration_ms = min_speech_duration_ms
        self.energy_threshold = energy_threshold
        self.sample_rate = sample_rate

        # State tracking
        self._speech_start: Optional[float] = None
        self._speech_samples = 0
        self._is_playing = False
        self._last_energy = 0.0

    def reset(self) -> None:
        """Reset detector state for new playback session."""
        self._speech_start = None
        self._speech_samples = 0
        self._is_playing = False
        self._last_energy = 0.0
        log.debug("barge_in_detector_reset")

    def set_playing(self, is_playing: bool) -> None:
        """Update playback state.

        Args:
            is_playing: True if TTS is currently playing
        """
        if is_playing and not self._is_playing:
            # Starting playback - reset speech detection
            self._speech_start = None
            self._speech_samples = 0
            log.debug("barge_in_playback_started")
        elif not is_playing and self._is_playing:
            log.debug("barge_in_playback_stopped")

        self._is_playing = is_playing

    def process_chunk(
        self,
        audio: np.ndarray,
        is_playing: bool = True,
    ) -> BargeInResult:
        """Process audio chunk and detect barge-in.

        Args:
            audio: Audio samples as float32 numpy array, normalized to [-1, 1]
            is_playing: Whether TTS is currently playing

        Returns:
            BargeInResult with detection status
        """
        # Update playing state
        self.set_playing(is_playing)

        # Calculate RMS energy
        if len(audio) == 0:
            return BargeInResult(
                detected=False,
                speech_duration_ms=0,
                energy=0.0,
                latency_ms=0.0,
            )

        # Convert to float32 if needed
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Normalize if needed
        if np.abs(audio).max() > 1.0:
            audio = audio / 32768.0

        # Calculate RMS energy
        energy = np.sqrt(np.mean(audio ** 2))
        self._last_energy = energy

        # Only detect during playback
        if not is_playing:
            self._speech_start = None
            self._speech_samples = 0
            return BargeInResult(
                detected=False,
                speech_duration_ms=0,
                energy=energy,
                latency_ms=0.0,
            )

        # Check if energy exceeds threshold
        if energy > self.energy_threshold:
            # Speech detected
            if self._speech_start is None:
                self._speech_start = time.perf_counter()
                self._speech_samples = len(audio)
                log.debug("barge_in_speech_started", energy=energy)
            else:
                self._speech_samples += len(audio)

            # Calculate duration
            speech_duration_ms = int(self._speech_samples / self.sample_rate * 1000)
            latency_ms = (time.perf_counter() - self._speech_start) * 1000

            # Check if we've accumulated enough speech
            if speech_duration_ms >= self.min_speech_duration_ms:
                log.info(
                    "barge_in_detected",
                    speech_duration_ms=speech_duration_ms,
                    latency_ms=round(latency_ms, 1),
                    energy=round(energy, 4),
                )
                return BargeInResult(
                    detected=True,
                    speech_duration_ms=speech_duration_ms,
                    energy=energy,
                    latency_ms=latency_ms,
                )

            return BargeInResult(
                detected=False,
                speech_duration_ms=speech_duration_ms,
                energy=energy,
                latency_ms=latency_ms,
            )
        else:
            # No speech - reset tracking
            if self._speech_start is not None:
                log.debug("barge_in_speech_stopped", energy=energy)
            self._speech_start = None
            self._speech_samples = 0

            return BargeInResult(
                detected=False,
                speech_duration_ms=0,
                energy=energy,
                latency_ms=0.0,
            )

    @property
    def is_detecting(self) -> bool:
        """Check if currently detecting speech during playback."""
        return self._is_playing and self._speech_start is not None


def create_barge_in_detector(
    min_speech_duration_ms: int = 150,
    energy_threshold: float = 0.02,
) -> BargeInDetector:
    """Factory function to create a BargeInDetector.

    Args:
        min_speech_duration_ms: Minimum speech to trigger (default: 150ms)
        energy_threshold: Energy threshold for speech (default: 0.02)

    Returns:
        Configured BargeInDetector instance
    """
    return BargeInDetector(
        min_speech_duration_ms=min_speech_duration_ms,
        energy_threshold=energy_threshold,
    )
