from __future__ import annotations

import base64
import io
import wave
from dataclasses import dataclass
from typing import Optional


@dataclass
class ValidationResult:
    """Result of audio validation."""

    valid: bool
    sample_rate: int
    channels: int
    duration_ms: int
    error: Optional[str] = None


class AudioValidator:
    """Validates WAV audio format."""

    def __init__(
        self, expected_sample_rate: int = 16000, expected_channels: int = 1
    ) -> None:
        self.expected_sample_rate = expected_sample_rate
        self.expected_channels = expected_channels

    def validate(self, audio_base64: str) -> ValidationResult:
        """
        Validate base64 encoded WAV audio data.

        Args:
            audio_base64: Base64 encoded WAV audio data

        Returns:
            ValidationResult with validation status and audio metadata
        """
        try:
            # Decode base64
            audio_bytes = base64.b64decode(audio_base64)

            # Parse WAV header
            with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
                sample_rate = wav.getframerate()
                channels = wav.getnchannels()
                frames = wav.getnframes()
                sample_width = wav.getsampwidth()

                # Calculate duration
                duration_ms = int((frames / sample_rate) * 1000) if sample_rate > 0 else 0

                # Validate sample rate
                if sample_rate != self.expected_sample_rate:
                    return ValidationResult(
                        valid=False,
                        sample_rate=sample_rate,
                        channels=channels,
                        duration_ms=duration_ms,
                        error=f"Expected {self.expected_sample_rate}Hz, got {sample_rate}Hz",
                    )

                # Validate channels
                if channels != self.expected_channels:
                    return ValidationResult(
                        valid=False,
                        sample_rate=sample_rate,
                        channels=channels,
                        duration_ms=duration_ms,
                        error=f"Expected {self.expected_channels} channel(s), got {channels}",
                    )

                # Validate sample width (16-bit = 2 bytes)
                if sample_width != 2:
                    return ValidationResult(
                        valid=False,
                        sample_rate=sample_rate,
                        channels=channels,
                        duration_ms=duration_ms,
                        error=f"Expected 16-bit audio (2 bytes), got {sample_width * 8}-bit ({sample_width} bytes)",
                    )

                return ValidationResult(
                    valid=True,
                    sample_rate=sample_rate,
                    channels=channels,
                    duration_ms=duration_ms,
                )

        except base64.binascii.Error as e:
            return ValidationResult(
                valid=False,
                sample_rate=0,
                channels=0,
                duration_ms=0,
                error=f"Invalid base64 encoding: {e}",
            )
        except wave.Error as e:
            return ValidationResult(
                valid=False,
                sample_rate=0,
                channels=0,
                duration_ms=0,
                error=f"Invalid WAV format: {e}",
            )
        except Exception as e:
            return ValidationResult(
                valid=False,
                sample_rate=0,
                channels=0,
                duration_ms=0,
                error=f"Validation error: {e}",
            )
