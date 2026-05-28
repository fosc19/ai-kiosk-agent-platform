from __future__ import annotations

import base64
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from audio_validator import AudioValidator
from config import settings

# F8: Tracing
try:
    from tracing_setup import setup_tracing, Events, SpeechTracer
    tracer: SpeechTracer | None = setup_tracing()
except ImportError:
    tracer = None
    Events = None

# Configure structured logging
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, settings.log_level)
    ),
    logger_factory=structlog.PrintLoggerFactory(),
)

log = structlog.get_logger()

# Global pipeline instance (initialized in lifespan)
speech_pipeline = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global speech_pipeline

    # Startup
    log.info("speech_service_starting", port=settings.port)

    # Create debug audio directory if needed
    if settings.debug_save_audio:
        os.makedirs(settings.audio_save_path, exist_ok=True)
        log.info("debug_audio_enabled", path=settings.audio_save_path)

    try:
        import asyncio

        from asr.factory import create_asr_provider
        from pipeline import SpeechPipeline
        from tts.cache import CachedTTSProvider, DEFAULT_CACHED_PHRASES, TTSCacheConfig
        from tts.factory import create_tts_provider
        from vad import SileroVAD

        # VAD (always local - Silero)
        vad = SileroVAD(
            threshold=settings.vad_threshold,
            min_speech_ms=settings.vad_min_speech_ms,
            min_silence_ms=settings.vad_min_silence_ms,
        )

        # ASR via factory (local or deepgram)
        log.info("creating_asr", mode=settings.asr_mode)
        asr = create_asr_provider(
            mode=settings.asr_mode,
            language=settings.asr_language,
            deepgram_api_key=settings.deepgram_api_key,
            deepgram_model=settings.asr_model,
            whisper_model_size=settings.whisper_model_size,
            whisper_device=settings.whisper_device,
            whisper_compute_type=settings.whisper_compute_type,
            whisper_prompt=settings.whisper_prompt,
            enable_fallback=settings.enable_fallback,
        )

        # TTS via factory (local or elevenlabs)
        log.info("creating_tts", mode=settings.tts_mode)
        tts = create_tts_provider(
            mode=settings.tts_mode,
            elevenlabs_api_key=settings.elevenlabs_api_key,
            elevenlabs_voice_id=settings.tts_voice_id,
            elevenlabs_model_id=settings.tts_model_id,
            piper_model_path=settings.piper_model_path,
            piper_speaker_id=settings.piper_speaker_id,
            enable_fallback=settings.enable_fallback,
        )

        # Wrap TTS with cache if enabled
        if settings.tts_cache_enabled:
            cache_config = TTSCacheConfig(
                cache_dir=settings.tts_cache_dir,
                preload_phrases=DEFAULT_CACHED_PHRASES if settings.tts_cache_preload else [],
                persist_to_disk=True,
            )
            tts = CachedTTSProvider(provider=tts, config=cache_config)

            # Preload cache in background
            if settings.tts_cache_preload:
                asyncio.create_task(tts.preload_cache())

        speech_pipeline = SpeechPipeline(vad=vad, asr=asr, tts=tts)
        log.info(
            "speech_pipeline_initialized",
            asr_mode=settings.asr_mode,
            tts_mode=settings.tts_mode,
            tts_cache_enabled=settings.tts_cache_enabled,
        )
    except Exception as e:
        log.error("speech_pipeline_init_failed", error=str(e))
        # Service can still start but pipeline endpoints will return 503

    yield

    # Shutdown
    log.info("speech_service_stopped")


app = FastAPI(
    title="Speech Service",
    description="Audio validation, VAD, ASR, TTS service",
    version="0.1.0",
    lifespan=lifespan,
)


class ValidateAudioRequest(BaseModel):
    """Request body for audio validation endpoint."""

    audio_data: str  # base64 WAV
    session_id: str
    turn_id: str


class ValidateAudioResponse(BaseModel):
    """Response body for audio validation endpoint."""

    valid: bool
    sample_rate: int
    channels: int
    duration_ms: int
    error: Optional[str] = None


@app.get("/healthz")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "speech",
        "version": "0.1.0",
    }


@app.post("/validate-audio", response_model=ValidateAudioResponse)
async def validate_audio(request: ValidateAudioRequest):
    """
    Validate audio format.

    Expects 16kHz mono PCM WAV encoded as base64.
    Optionally saves audio to disk if DEBUG_SAVE_AUDIO is enabled.
    """
    validator = AudioValidator(
        expected_sample_rate=settings.expected_sample_rate,
        expected_channels=settings.expected_channels,
    )

    result = validator.validate(request.audio_data)

    # Save debug audio if enabled and valid
    if settings.debug_save_audio and result.valid:
        _save_debug_audio(request.audio_data, request.session_id, request.turn_id)

    log.info(
        "audio_validated",
        session_id=request.session_id,
        turn_id=request.turn_id,
        valid=result.valid,
        sample_rate=result.sample_rate,
        channels=result.channels,
        duration_ms=result.duration_ms,
        error=result.error,
    )

    return ValidateAudioResponse(
        valid=result.valid,
        sample_rate=result.sample_rate,
        channels=result.channels,
        duration_ms=result.duration_ms,
        error=result.error,
    )


# ============================================================
# F3: VAD, ASR, TTS endpoints
# ============================================================


class ProcessChunkRequest(BaseModel):
    """Request for VAD chunk processing."""

    chunk_data: str  # base64 PCM audio
    session_id: str
    turn_id: str


class ProcessChunkResponse(BaseModel):
    """Response from VAD processing."""

    is_speech: bool
    confidence: float
    speech_duration_ms: int
    silence_duration_ms: int
    end_of_speech: bool


class TranscribeRequest(BaseModel):
    """Request for ASR transcription."""

    session_id: str
    turn_id: str


class TranscribeResponse(BaseModel):
    """Response from ASR transcription."""

    text: str
    confidence: float
    duration_ms: int
    language: str


class SynthesizeRequest(BaseModel):
    """Request for TTS synthesis."""

    text: str
    session_id: str
    turn_id: str
    stream: bool = False


class SynthesizeResponse(BaseModel):
    """Response from TTS synthesis."""

    audio_data: str  # base64 MP3
    duration_ms: int


@app.post("/process-chunk", response_model=ProcessChunkResponse)
async def process_chunk(request: ProcessChunkRequest):
    """Process audio chunk through VAD.

    Returns speech detection result including end_of_speech flag.
    """
    if speech_pipeline is None:
        raise HTTPException(status_code=503, detail="Speech pipeline not initialized")

    try:
        result = speech_pipeline.process_chunk(
            chunk_data=request.chunk_data,
            session_id=request.session_id,
        )

        # F8: Emit VAD traces
        if tracer and result.is_speech and result.speech_duration_ms <= 100:
            # First speech detection - emit VAD_START
            tracer.emit(
                Events.VAD_START,
                trace_id=request.session_id,
                turn_id=request.turn_id,
            )

        if tracer and result.end_of_speech:
            # End of speech - emit VAD_END
            tracer.emit(
                Events.VAD_END,
                trace_id=request.session_id,
                turn_id=request.turn_id,
                speech_duration_ms=result.speech_duration_ms,
            )

        # Log VAD state for debugging (only when interesting)
        if result.is_speech or result.end_of_speech or (result.silence_duration_ms > 0 and result.silence_duration_ms % 200 == 0):
            log.info(
                "vad_state",
                session_id=request.session_id,
                is_speech=result.is_speech,
                confidence=f"{result.confidence:.3f}",
                speech_ms=result.speech_duration_ms,
                silence_ms=result.silence_duration_ms,
                end_of_speech=result.end_of_speech,
            )

        return ProcessChunkResponse(
            is_speech=result.is_speech,
            confidence=result.confidence,
            speech_duration_ms=result.speech_duration_ms,
            silence_duration_ms=result.silence_duration_ms,
            end_of_speech=result.end_of_speech,
        )
    except Exception as e:
        log.error("process_chunk_error", error=str(e), session_id=request.session_id)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(request: TranscribeRequest):
    """Transcribe buffered audio using ASR.

    Call this after receiving end_of_speech from /process-chunk.
    """
    if speech_pipeline is None:
        raise HTTPException(status_code=503, detail="Speech pipeline not initialized")

    try:
        # DEBUG: Guardar audio de buffer final ANTES de transcribir
        if settings.debug_save_audio:
            buffer = speech_pipeline.get_buffer(request.session_id)
            audio_bytes = buffer.get_audio()
            if audio_bytes:
                _save_debug_audio_from_bytes(
                    audio_bytes,
                    request.session_id,
                    request.turn_id,
                    prefix="buffer_final"
                )
                log.debug("buffer_saved_for_debug",
                         session_id=request.session_id,
                         turn_id=request.turn_id,
                         buffer_duration_ms=buffer.duration_ms)

        # F8: Emit ASR start trace
        if tracer:
            tracer.emit(
                Events.ASR_START,
                trace_id=request.session_id,
                turn_id=request.turn_id,
            )

        result = await speech_pipeline.transcribe(session_id=request.session_id)

        # F8: Emit ASR final trace
        if tracer:
            tracer.emit(
                Events.ASR_FINAL,
                trace_id=request.session_id,
                turn_id=request.turn_id,
                text=result.text,
                confidence=result.confidence,
                duration_ms=result.duration_ms,
            )

        # Reset session after transcription
        speech_pipeline.reset_session(request.session_id)

        return TranscribeResponse(
            text=result.text,
            confidence=result.confidence,
            duration_ms=result.duration_ms,
            language=result.language,
        )
    except Exception as e:
        log.error("transcribe_error", error=str(e), session_id=request.session_id)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/synthesize")
async def synthesize(request: SynthesizeRequest):
    """Synthesize text to speech.

    If stream=true, returns streaming NDJSON with audio chunks.
    Otherwise returns complete audio as base64.
    """
    if speech_pipeline is None:
        raise HTTPException(status_code=503, detail="Speech pipeline not initialized")

    try:
        # F8: Emit TTS start trace
        if tracer:
            tracer.emit(
                Events.TTS_START,
                trace_id=request.session_id,
                turn_id=request.turn_id,
                text_length=len(request.text),
                stream=request.stream,
            )

        if request.stream:
            # Streaming response with NDJSON (newline-delimited JSON)
            # Uses look-ahead pattern to mark is_last correctly
            async def generate_chunks():
                prev_chunk = None
                prev_index = None
                first_chunk_emitted = False

                async for chunk, index in speech_pipeline.synthesize_stream(
                    text=request.text,
                    session_id=request.session_id,
                ):
                    # F8: Emit TTS first chunk trace
                    if not first_chunk_emitted and tracer:
                        tracer.emit(
                            Events.TTS_FIRST_CHUNK,
                            trace_id=request.session_id,
                            turn_id=request.turn_id,
                        )
                        first_chunk_emitted = True

                    # Send previous chunk (we now know it's not the last)
                    if prev_chunk is not None:
                        chunk_json = {
                            "audio": base64.b64encode(prev_chunk).decode(),
                            "chunk_index": prev_index,
                            "is_last": False,
                        }
                        yield json.dumps(chunk_json) + "\n"

                    prev_chunk = chunk
                    prev_index = index

                # Send the last chunk
                if prev_chunk is not None:
                    chunk_json = {
                        "audio": base64.b64encode(prev_chunk).decode(),
                        "chunk_index": prev_index,
                        "is_last": True,
                    }
                    yield json.dumps(chunk_json) + "\n"

                    # F8: Emit TTS end trace
                    if tracer:
                        tracer.emit(
                            Events.TTS_END,
                            trace_id=request.session_id,
                            turn_id=request.turn_id,
                            chunk_count=prev_index + 1 if prev_index is not None else 0,
                        )

            return StreamingResponse(
                generate_chunks(),
                media_type="application/x-ndjson",
                headers={"X-Turn-Id": request.turn_id},
            )
        else:
            # Complete audio response
            audio_bytes = await speech_pipeline.synthesize(
                text=request.text,
                session_id=request.session_id,
            )

            # F8: Emit TTS end trace for non-streaming
            if tracer:
                tracer.emit(
                    Events.TTS_END,
                    trace_id=request.session_id,
                    turn_id=request.turn_id,
                    audio_size=len(audio_bytes),
                )

            return SynthesizeResponse(
                audio_data=base64.b64encode(audio_bytes).decode(),
                duration_ms=speech_pipeline.get_metrics(request.session_id).total_latency_ms,
            )
    except Exception as e:
        log.error("synthesize_error", error=str(e), session_id=request.session_id)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reset-session")
async def reset_session(session_id: str):
    """Reset session state (buffer, VAD state)."""
    if speech_pipeline is None:
        raise HTTPException(status_code=503, detail="Speech pipeline not initialized")

    speech_pipeline.reset_session(session_id)
    return {"status": "ok", "session_id": session_id}


# ============================================================
# F6: Barge-in detection endpoints
# ============================================================


class SetPlaybackStateRequest(BaseModel):
    """Request to set playback state."""

    session_id: str
    is_playing: bool


class DetectBargeInRequest(BaseModel):
    """Request for barge-in detection."""

    chunk_data: str  # base64 PCM audio
    session_id: str


class DetectBargeInResponse(BaseModel):
    """Response from barge-in detection."""

    detected: bool
    speech_duration_ms: int
    energy: float
    latency_ms: float


@app.post("/set-playback-state")
async def set_playback_state(request: SetPlaybackStateRequest):
    """Set playback state for barge-in detection.

    Call this when TTS starts/stops playing.
    """
    if speech_pipeline is None:
        raise HTTPException(status_code=503, detail="Speech pipeline not initialized")

    speech_pipeline.set_playback_state(request.session_id, request.is_playing)
    return {"status": "ok", "session_id": request.session_id, "is_playing": request.is_playing}


@app.post("/detect-barge-in", response_model=DetectBargeInResponse)
async def detect_barge_in(request: DetectBargeInRequest):
    """Detect if user is speaking during TTS playback.

    Returns barge-in detection result. If detected=True,
    the orchestrator should stop TTS playback immediately.
    """
    if speech_pipeline is None:
        raise HTTPException(status_code=503, detail="Speech pipeline not initialized")

    try:
        result = speech_pipeline.detect_barge_in(
            chunk_data=request.chunk_data,
            session_id=request.session_id,
        )

        return DetectBargeInResponse(
            detected=result.detected,
            speech_duration_ms=result.speech_duration_ms,
            energy=result.energy,
            latency_ms=result.latency_ms,
        )
    except Exception as e:
        log.error("detect_barge_in_error", error=str(e), session_id=request.session_id)
        raise HTTPException(status_code=500, detail=str(e))


def _save_debug_audio(audio_base64: str, session_id: str, turn_id: str) -> None:
    """Save audio to disk for debugging."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{session_id}_{turn_id}_{timestamp}.wav"
        filepath = os.path.join(settings.audio_save_path, filename)

        audio_bytes = base64.b64decode(audio_base64)
        with open(filepath, "wb") as f:
            f.write(audio_bytes)

        log.debug("debug_audio_saved", filepath=filepath)
    except Exception as e:
        log.warning("debug_audio_save_failed", error=str(e))


def _save_debug_audio_from_bytes(
    audio_bytes: bytes,
    session_id: str,
    turn_id: str,
    prefix: str = "chunk"
) -> None:
    """Save raw PCM audio bytes as WAV for debugging.

    Args:
        audio_bytes: Raw PCM audio bytes (16-bit, mono, 16kHz)
        session_id: Session identifier
        turn_id: Turn identifier
        prefix: Filename prefix (e.g. "buffer_final", "chunk")
    """
    if not settings.debug_save_audio:
        return

    try:
        import wave
        from pipeline import SAMPLE_RATE

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{prefix}_{session_id}_{turn_id}_{timestamp}.wav"
        filepath = os.path.join(settings.audio_save_path, filename)

        # Create WAV with header
        with wave.open(filepath, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(SAMPLE_RATE)  # 16kHz
            wav_file.writeframes(audio_bytes)

        log.debug("debug_audio_saved", filepath=filepath, size=len(audio_bytes))
    except Exception as e:
        log.error("debug_audio_save_failed", error=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
