"""Tests for BargeInDetector - F6 interruption detection."""

import numpy as np
import pytest
import time

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "services" / "speech"))

from vad.barge_in_detector import BargeInDetector, BargeInResult, create_barge_in_detector


class TestBargeInDetector:
    """Test BargeInDetector speech detection during playback."""

    @pytest.fixture
    def detector(self):
        """Create detector with test settings."""
        return BargeInDetector(
            min_speech_duration_ms=100,  # Faster for tests
            energy_threshold=0.02,
            sample_rate=16000,
        )

    def _generate_silence(self, duration_ms: int, sample_rate: int = 16000) -> np.ndarray:
        """Generate silent audio (near-zero energy)."""
        samples = int(sample_rate * duration_ms / 1000)
        return np.zeros(samples, dtype=np.float32)

    def _generate_speech(self, duration_ms: int, amplitude: float = 0.5, sample_rate: int = 16000) -> np.ndarray:
        """Generate speech-like audio (sine wave with noise)."""
        samples = int(sample_rate * duration_ms / 1000)
        t = np.linspace(0, duration_ms / 1000, samples)
        # Mix of frequencies to simulate speech
        signal = amplitude * (
            0.5 * np.sin(2 * np.pi * 200 * t) +
            0.3 * np.sin(2 * np.pi * 400 * t) +
            0.2 * np.random.randn(samples) * 0.1
        )
        return signal.astype(np.float32)

    def _generate_noise(self, duration_ms: int, amplitude: float = 0.01, sample_rate: int = 16000) -> np.ndarray:
        """Generate low-level noise (below threshold)."""
        samples = int(sample_rate * duration_ms / 1000)
        return (np.random.randn(samples) * amplitude).astype(np.float32)

    # === Basic Detection ===

    def test_no_detection_when_not_playing(self, detector):
        """Test no barge-in detected when not in playback mode."""
        speech = self._generate_speech(200)

        result = detector.process_chunk(speech, is_playing=False)

        assert not result.detected
        assert result.speech_duration_ms == 0

    def test_no_detection_on_silence(self, detector):
        """Test no barge-in detected on silence during playback."""
        silence = self._generate_silence(200)

        result = detector.process_chunk(silence, is_playing=True)

        assert not result.detected
        assert result.energy < detector.energy_threshold

    def test_no_detection_on_noise(self, detector):
        """Test no barge-in on low-level noise during playback."""
        noise = self._generate_noise(200, amplitude=0.005)

        result = detector.process_chunk(noise, is_playing=True)

        assert not result.detected
        assert result.energy < detector.energy_threshold

    def test_detection_on_sustained_speech(self, detector):
        """Test barge-in detected on sustained speech during playback."""
        # First chunk starts accumulating
        speech1 = self._generate_speech(50)
        result1 = detector.process_chunk(speech1, is_playing=True)
        assert not result1.detected  # Not enough duration yet

        # Second chunk reaches threshold
        speech2 = self._generate_speech(100)
        result2 = detector.process_chunk(speech2, is_playing=True)

        assert result2.detected
        assert result2.speech_duration_ms >= detector.min_speech_duration_ms

    # === Duration Threshold ===

    def test_short_speech_not_detected(self, detector):
        """Test short speech burst doesn't trigger barge-in."""
        # Just under threshold
        short_speech = self._generate_speech(50)

        result = detector.process_chunk(short_speech, is_playing=True)

        assert not result.detected
        assert result.speech_duration_ms < detector.min_speech_duration_ms

    def test_duration_accumulates(self, detector):
        """Test speech duration accumulates across chunks."""
        chunk_ms = 30
        chunks_needed = detector.min_speech_duration_ms // chunk_ms + 1

        for i in range(chunks_needed):
            speech = self._generate_speech(chunk_ms)
            result = detector.process_chunk(speech, is_playing=True)

            if i == chunks_needed - 1:
                assert result.detected
            else:
                assert not result.detected

    # === State Management ===

    def test_reset_clears_state(self, detector):
        """Test reset clears accumulated speech duration."""
        # Accumulate some speech
        speech = self._generate_speech(80)
        detector.process_chunk(speech, is_playing=True)

        # Reset
        detector.reset()

        # Should start fresh
        speech2 = self._generate_speech(50)
        result = detector.process_chunk(speech2, is_playing=True)

        assert result.speech_duration_ms == 50  # Not 130

    def test_silence_resets_accumulation(self, detector):
        """Test silence resets speech accumulation."""
        # Start with speech
        speech = self._generate_speech(50)
        detector.process_chunk(speech, is_playing=True)

        # Silence interrupts
        silence = self._generate_silence(50)
        result = detector.process_chunk(silence, is_playing=True)

        assert result.speech_duration_ms == 0

        # New speech starts fresh
        speech2 = self._generate_speech(50)
        result2 = detector.process_chunk(speech2, is_playing=True)

        assert result2.speech_duration_ms == 50

    def test_playback_state_change_resets(self, detector):
        """Test switching from not playing to playing resets state."""
        # Accumulate while not playing (shouldn't count)
        speech = self._generate_speech(100)
        detector.process_chunk(speech, is_playing=False)

        # Start playing
        speech2 = self._generate_speech(50)
        result = detector.process_chunk(speech2, is_playing=True)

        # Should only count the 50ms during playback
        assert result.speech_duration_ms == 50

    # === Latency ===

    def test_latency_tracking(self, detector):
        """Test latency from first speech to detection is tracked."""
        # First chunk
        speech1 = self._generate_speech(50)
        result1 = detector.process_chunk(speech1, is_playing=True)

        assert result1.latency_ms > 0

        # Allow some time to pass
        time.sleep(0.01)

        # Second chunk
        speech2 = self._generate_speech(100)
        result2 = detector.process_chunk(speech2, is_playing=True)

        assert result2.latency_ms > result1.latency_ms
        assert result2.detected

    # === Properties ===

    def test_is_detecting_property(self, detector):
        """Test is_detecting property."""
        assert not detector.is_detecting

        # Start detecting
        speech = self._generate_speech(50)
        detector.process_chunk(speech, is_playing=True)

        assert detector.is_detecting

        # Stop playback
        detector.set_playing(False)
        assert not detector.is_detecting

    # === Factory ===

    def test_factory_creates_detector(self):
        """Test factory function creates detector."""
        detector = create_barge_in_detector(
            min_speech_duration_ms=200,
            energy_threshold=0.03,
        )

        assert detector.min_speech_duration_ms == 200
        assert detector.energy_threshold == 0.03

    # === Edge Cases ===

    def test_empty_audio(self, detector):
        """Test handling empty audio array."""
        empty = np.array([], dtype=np.float32)

        result = detector.process_chunk(empty, is_playing=True)

        assert not result.detected
        assert result.energy == 0.0

    def test_16bit_pcm_normalization(self, detector):
        """Test 16-bit PCM audio is normalized correctly."""
        # Generate 16-bit range audio
        samples = 800
        audio = (np.random.randn(samples) * 16000).astype(np.float32)

        result = detector.process_chunk(audio, is_playing=True)

        # Should have been normalized and have reasonable energy
        assert result.energy < 1.0  # Normalized

    # === F6 Performance Requirements ===

    def test_barge_in_latency_under_200ms(self, detector):
        """Test F6 requirement: barge-in detection latency < 200ms.

        This tests that the detector identifies barge-in quickly enough
        for responsive interruption handling.
        """
        # Configure for 150ms detection (F6 default)
        fast_detector = BargeInDetector(
            min_speech_duration_ms=150,
            energy_threshold=0.02,
            sample_rate=16000,
        )

        start_time = time.perf_counter()

        # Simulate speech chunks coming in
        # First chunk: 100ms of speech
        speech1 = self._generate_speech(100)
        result1 = fast_detector.process_chunk(speech1, is_playing=True)
        assert not result1.detected

        # Second chunk: 100ms more (total 200ms > 150ms threshold)
        speech2 = self._generate_speech(100)
        result2 = fast_detector.process_chunk(speech2, is_playing=True)

        detection_time_ms = (time.perf_counter() - start_time) * 1000

        assert result2.detected, "Should detect barge-in after 200ms of speech"
        assert result2.latency_ms < 200, f"Latency {result2.latency_ms}ms should be < 200ms"
        assert detection_time_ms < 200, f"Total detection time {detection_time_ms}ms should be < 200ms"

    def test_no_false_positives_on_brief_sounds(self, detector):
        """Test that brief sounds don't trigger false barge-in.

        F6: Requires min_speech_duration_ms (150ms default) to avoid
        triggering on coughs, clicks, or TTS feedback.
        """
        detector_150ms = BargeInDetector(
            min_speech_duration_ms=150,
            energy_threshold=0.02,
            sample_rate=16000,
        )

        # Brief 50ms sound (e.g., click, cough) - should NOT trigger
        brief_sound = self._generate_speech(50, amplitude=0.5)
        result = detector_150ms.process_chunk(brief_sound, is_playing=True)
        assert not result.detected, "Brief 50ms sound should not trigger barge-in"

        # Reset with silence
        silence = self._generate_silence(100)
        detector_150ms.process_chunk(silence, is_playing=True)

        # Another brief 80ms sound - still should NOT trigger
        brief_sound2 = self._generate_speech(80)
        result2 = detector_150ms.process_chunk(brief_sound2, is_playing=True)
        assert not result2.detected, "Brief 80ms sound should not trigger barge-in"
