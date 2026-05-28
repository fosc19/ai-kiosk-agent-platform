"""Speech pipeline coordinating VAD, ASR, and TTS."""

from __future__ import annotations

import base64
import io
import time
import wave
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

import numpy as np
import structlog

from asr import ASRProvider, TranscriptResult
from tts import TTSProvider
from vad import SileroVAD, VADResult
from vad.barge_in_detector import BargeInDetector, BargeInResult

log = structlog.get_logger()

SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2  # 16-bit audio


def extract_pcm_from_wav(wav_bytes: bytes) -> bytes:
    """Extract raw PCM data from WAV bytes.

    Args:
        wav_bytes: WAV file bytes (with header)

    Returns:
        Raw PCM audio bytes (no header)
    """
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            return wav_file.readframes(wav_file.getnframes())
    except wave.Error:
        # If it's not a valid WAV, assume it's already raw PCM
        return wav_bytes


@dataclass
class PipelineMetrics:
    """Timing metrics for pipeline operations."""

    vad_end_ms: int = 0
    asr_duration_ms: int = 0
    tts_first_chunk_ms: int = 0
    total_latency_ms: int = 0


@dataclass
class AudioBuffer:
    """Buffer for accumulating audio chunks with gating.

    Buffer gating ensures we only accumulate audio when VAD detects speech,
    avoiding long silences and noise before the user speaks.
    """

    chunks: list[bytes] = field(default_factory=list)
    total_samples: int = 0

    # Pre-roll circular buffer (captures 500ms before speech detection)
    pre_roll_buffer: list[bytes] = field(default_factory=list)
    pre_roll_samples: int = 0
    PRE_ROLL_MS: int = 500
    MAX_BUFFER_MS: int = 15000  # Limit buffer to 15s

    is_gated: bool = True  # Start gated (don't accumulate)

    def add(self, chunk: bytes) -> None:
        """Add audio chunk to buffer (legacy method without gating).

        This method is kept for backward compatibility but should
        be replaced with add_with_gating() for better quality.
        """
        self.chunks.append(chunk)
        self.total_samples += len(chunk) // BYTES_PER_SAMPLE

    def add_with_gating(self, chunk: bytes, is_speech: bool) -> None:
        """Add chunk with gating - only buffer when VAD detects speech.

        Args:
            chunk: Audio chunk bytes (raw PCM)
            is_speech: Whether VAD detected speech in this chunk
        """
        # Always maintain pre-roll circular buffer
        self.pre_roll_buffer.append(chunk)
        self.pre_roll_samples += len(chunk) // BYTES_PER_SAMPLE

        # Trim pre-roll to PRE_ROLL_MS
        pre_roll_max_samples = int((self.PRE_ROLL_MS / 1000) * SAMPLE_RATE)
        while self.pre_roll_samples > pre_roll_max_samples and len(self.pre_roll_buffer) > 0:
            removed = self.pre_roll_buffer.pop(0)
            self.pre_roll_samples -= len(removed) // BYTES_PER_SAMPLE

        # If VAD detects speech and we're gated, open gate and dump pre-roll
        if is_speech and self.is_gated:
            log.info("buffer_gate_opened", pre_roll_samples=self.pre_roll_samples)
            self.is_gated = False
            # Dump pre-roll into main buffer
            for pre_chunk in self.pre_roll_buffer:
                self.chunks.append(pre_chunk)
                self.total_samples += len(pre_chunk) // BYTES_PER_SAMPLE
            self.pre_roll_buffer.clear()
            self.pre_roll_samples = 0

        # If gate is open, continue accumulating
        if not self.is_gated:
            self.chunks.append(chunk)
            self.total_samples += len(chunk) // BYTES_PER_SAMPLE

            # Trim if exceeds MAX_BUFFER_MS
            max_samples = int((self.MAX_BUFFER_MS / 1000) * SAMPLE_RATE)
            while self.total_samples > max_samples and len(self.chunks) > 0:
                removed = self.chunks.pop(0)
                self.total_samples -= len(removed) // BYTES_PER_SAMPLE
                log.warning("buffer_truncated",
                           new_duration_ms=self.duration_ms,
                           max_ms=self.MAX_BUFFER_MS)

    def get_audio(self) -> bytes:
        """Get all buffered audio as bytes."""
        return b"".join(self.chunks)

    def get_numpy(self) -> np.ndarray:
        """Get all buffered audio as numpy array."""
        audio_bytes = self.get_audio()
        return np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    def clear(self) -> None:
        """Clear the buffer."""
        self.chunks.clear()
        self.total_samples = 0
        self.pre_roll_buffer.clear()
        self.pre_roll_samples = 0
        self.is_gated = True  # Reset to gated state

    @property
    def duration_ms(self) -> int:
        """Get buffer duration in milliseconds."""
        return int(self.total_samples / SAMPLE_RATE * 1000)


class SpeechPipeline:
    """Coordinates VAD -> ASR -> TTS pipeline."""

    def __init__(
        self,
        vad: SileroVAD,
        asr: ASRProvider,
        tts: TTSProvider,
        barge_in_min_duration_ms: int = 150,
        barge_in_energy_threshold: float = 0.02,
    ):
        """Initialize speech pipeline.

        Args:
            vad: VAD instance for voice activity detection
            asr: ASR provider for transcription
            tts: TTS provider for speech synthesis
            barge_in_min_duration_ms: F6 - Minimum speech for barge-in
            barge_in_energy_threshold: F6 - Energy threshold for barge-in
        """
        self.vad = vad
        self.asr = asr
        self.tts = tts

        # F6: Barge-in detector
        self.barge_in_detector = BargeInDetector(
            min_speech_duration_ms=barge_in_min_duration_ms,
            energy_threshold=barge_in_energy_threshold,
        )

        # Per-session state
        self._buffers: dict[str, AudioBuffer] = {}
        self._metrics: dict[str, PipelineMetrics] = {}
        self._playback_state: dict[str, bool] = {}  # F6: Track playback per session

    def get_buffer(self, session_id: str) -> AudioBuffer:
        """Get or create buffer for session."""
        if session_id not in self._buffers:
            self._buffers[session_id] = AudioBuffer()
        return self._buffers[session_id]

    def get_metrics(self, session_id: str) -> PipelineMetrics:
        """Get or create metrics for session."""
        if session_id not in self._metrics:
            self._metrics[session_id] = PipelineMetrics()
        return self._metrics[session_id]

    def reset_session(self, session_id: str) -> None:
        """Reset session state."""
        if session_id in self._buffers:
            self._buffers[session_id].clear()
        if session_id in self._metrics:
            self._metrics[session_id] = PipelineMetrics()
        if session_id in self._playback_state:
            self._playback_state[session_id] = False
        self.vad.reset()
        self.barge_in_detector.reset()

    # F6: Barge-in detection methods

    def set_playback_state(self, session_id: str, is_playing: bool) -> None:
        """Set playback state for session (for barge-in detection).

        Args:
            session_id: Session identifier
            is_playing: Whether TTS is currently playing
        """
        self._playback_state[session_id] = is_playing
        self.barge_in_detector.set_playing(is_playing)

        if is_playing:
            log.debug("playback_started", session_id=session_id)
        else:
            log.debug("playback_stopped", session_id=session_id)

    def is_playing(self, session_id: str) -> bool:
        """Check if session is in playback mode."""
        return self._playback_state.get(session_id, False)

    def detect_barge_in(
        self,
        chunk_data: str,
        session_id: str,
    ) -> BargeInResult:
        """Detect if user is speaking during TTS playback.

        Args:
            chunk_data: Base64 encoded WAV audio
            session_id: Session identifier

        Returns:
            BargeInResult with detection info
        """
        # Decode base64 to WAV bytes
        wav_bytes = base64.b64decode(chunk_data)

        # Extract raw PCM from WAV (strip header)
        pcm_bytes = extract_pcm_from_wav(wav_bytes)

        # Convert to numpy
        audio_np = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        # Check if in playback mode
        is_playing = self._playback_state.get(session_id, False)

        # Process through barge-in detector
        result = self.barge_in_detector.process_chunk(audio_np, is_playing=is_playing)

        if result.detected:
            log.info(
                "barge_in_detected",
                session_id=session_id,
                speech_duration_ms=result.speech_duration_ms,
                latency_ms=round(result.latency_ms, 1),
            )

        return result

    def process_chunk(
        self,
        chunk_data: str,  # base64 encoded WAV
        session_id: str,
    ) -> VADResult:
        """Process audio chunk through VAD.

        Args:
            chunk_data: Base64 encoded WAV audio
            session_id: Session identifier

        Returns:
            VADResult with speech detection info
        """
        # Decode base64 to WAV bytes
        wav_bytes = base64.b64decode(chunk_data)

        # Extract raw PCM from WAV (strip header)
        pcm_bytes = extract_pcm_from_wav(wav_bytes)

        # Convert to numpy for VAD
        audio_np = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        # Process through VAD
        result = self.vad.process_chunk(audio_np)

        # Add PCM to buffer with gating (only buffer when VAD detects speech)
        buffer = self.get_buffer(session_id)
        buffer.add_with_gating(pcm_bytes, result.is_speech)

        if result.end_of_speech:
            metrics = self.get_metrics(session_id)
            metrics.vad_end_ms = int(time.time() * 1000)

            log.info(
                "vad_end_of_speech",
                session_id=session_id,
                speech_duration_ms=result.speech_duration_ms,
                buffer_duration_ms=buffer.duration_ms,
            )

        return result

    async def transcribe(self, session_id: str) -> TranscriptResult:
        """Transcribe buffered audio.

        Args:
            session_id: Session identifier

        Returns:
            TranscriptResult with transcription
        """
        buffer = self.get_buffer(session_id)
        metrics = self.get_metrics(session_id)

        start_time = time.time()

        # Get audio and transcribe
        audio_bytes = buffer.get_audio()
        result = await self.asr.transcribe(audio_bytes, SAMPLE_RATE)

        metrics.asr_duration_ms = result.duration_ms

        log.info(
            "pipeline_transcribed",
            session_id=session_id,
            text=result.text,
            confidence=result.confidence,
            asr_duration_ms=result.duration_ms,
        )

        return result

    async def synthesize(self, text: str, session_id: str) -> bytes:
        """Synthesize text to audio.

        Args:
            text: Text to synthesize
            session_id: Session identifier

        Returns:
            Audio bytes (MP3)
        """
        metrics = self.get_metrics(session_id)
        start_time = time.time()

        audio = await self.tts.synthesize(text)

        tts_duration = int((time.time() - start_time) * 1000)
        metrics.total_latency_ms = tts_duration

        log.info(
            "pipeline_synthesized",
            session_id=session_id,
            text_length=len(text),
            audio_bytes=len(audio),
            tts_duration_ms=tts_duration,
        )

        return audio

    async def synthesize_stream(
        self,
        text: str,
        session_id: str,
    ) -> AsyncIterator[tuple[bytes, int]]:
        """Synthesize text to audio in streaming chunks.

        Args:
            text: Text to synthesize
            session_id: Session identifier

        Yields:
            Tuple of (audio_chunk, chunk_index)
        """
        metrics = self.get_metrics(session_id)
        start_time = time.time()
        chunk_index = 0
        first_chunk = True

        async for chunk in self.tts.synthesize_stream(text):
            if first_chunk:
                metrics.tts_first_chunk_ms = int((time.time() - start_time) * 1000)
                first_chunk = False

            yield chunk, chunk_index
            chunk_index += 1

        metrics.total_latency_ms = int((time.time() - start_time) * 1000)

        log.info(
            "pipeline_stream_complete",
            session_id=session_id,
            chunk_count=chunk_index,
            first_chunk_ms=metrics.tts_first_chunk_ms,
            total_ms=metrics.total_latency_ms,
        )
