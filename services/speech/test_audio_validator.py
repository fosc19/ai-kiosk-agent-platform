"""Unit tests for audio validator."""

import base64
import io
import wave

import pytest

from audio_validator import AudioValidator, ValidationResult


def create_test_wav(
    sample_rate: int = 16000, channels: int = 1, duration_ms: int = 100
) -> str:
    """Create a test WAV file and return as base64."""
    num_frames = int(sample_rate * duration_ms / 1000)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)  # 16-bit
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * num_frames * channels)

    return base64.b64encode(buffer.getvalue()).decode()


class TestAudioValidator:
    """Tests for AudioValidator class."""

    def test_valid_audio(self):
        """Test validation of correctly formatted audio."""
        validator = AudioValidator()
        audio = create_test_wav(16000, 1, 500)

        result = validator.validate(audio)

        assert result.valid is True
        assert result.sample_rate == 16000
        assert result.channels == 1
        assert result.duration_ms == 500
        assert result.error is None

    def test_valid_audio_short(self):
        """Test validation of short audio."""
        validator = AudioValidator()
        audio = create_test_wav(16000, 1, 100)

        result = validator.validate(audio)

        assert result.valid is True
        assert result.duration_ms == 100

    def test_valid_audio_long(self):
        """Test validation of longer audio."""
        validator = AudioValidator()
        audio = create_test_wav(16000, 1, 5000)

        result = validator.validate(audio)

        assert result.valid is True
        assert result.duration_ms == 5000

    def test_wrong_sample_rate(self):
        """Test validation rejects wrong sample rate."""
        validator = AudioValidator(expected_sample_rate=16000)
        audio = create_test_wav(44100, 1, 100)

        result = validator.validate(audio)

        assert result.valid is False
        assert "Expected 16000Hz" in result.error
        assert "got 44100Hz" in result.error

    def test_wrong_sample_rate_8khz(self):
        """Test validation rejects 8kHz sample rate."""
        validator = AudioValidator(expected_sample_rate=16000)
        audio = create_test_wav(8000, 1, 100)

        result = validator.validate(audio)

        assert result.valid is False
        assert "Expected 16000Hz" in result.error

    def test_wrong_channels_stereo(self):
        """Test validation rejects stereo audio."""
        validator = AudioValidator(expected_channels=1)
        audio = create_test_wav(16000, 2, 100)

        result = validator.validate(audio)

        assert result.valid is False
        assert "Expected 1 channel" in result.error
        assert "got 2" in result.error

    def test_invalid_base64(self):
        """Test validation handles invalid base64."""
        validator = AudioValidator()

        result = validator.validate("not-valid-base64!!!")

        assert result.valid is False
        assert result.error is not None
        assert "base64" in result.error.lower() or "Invalid" in result.error

    def test_invalid_wav_format(self):
        """Test validation handles invalid WAV data."""
        validator = AudioValidator()
        # Valid base64 but not a WAV file
        invalid_data = base64.b64encode(b"this is not a wav file").decode()

        result = validator.validate(invalid_data)

        assert result.valid is False
        assert result.error is not None

    def test_empty_base64(self):
        """Test validation handles empty base64."""
        validator = AudioValidator()

        result = validator.validate("")

        assert result.valid is False
        assert result.error is not None

    def test_custom_expected_values(self):
        """Test validator with custom expected values."""
        validator = AudioValidator(expected_sample_rate=44100, expected_channels=2)
        audio = create_test_wav(44100, 2, 100)

        result = validator.validate(audio)

        assert result.valid is True
        assert result.sample_rate == 44100
        assert result.channels == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
