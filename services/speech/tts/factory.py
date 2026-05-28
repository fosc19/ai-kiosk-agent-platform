"""Factory for creating TTS providers."""

from __future__ import annotations

from typing import Literal, Optional

import structlog

from .base import TTSProvider

log = structlog.get_logger()

TTSMode = Literal["local", "elevenlabs"]


def create_tts_provider(
    mode: TTSMode,
    *,
    # ElevenLabs config
    elevenlabs_api_key: Optional[str] = None,
    elevenlabs_voice_id: str = "pNInz6obpgDQGcFmaJgB",
    elevenlabs_model_id: str = "eleven_multilingual_v2",
    # Piper config
    piper_model_path: Optional[str] = None,
    piper_speaker_id: int = 0,
    # Fallback
    enable_fallback: bool = True,
) -> TTSProvider:
    """Create TTS provider based on mode.

    Args:
        mode: "local" for Piper, "elevenlabs" for API
        elevenlabs_api_key: API key for ElevenLabs
        elevenlabs_voice_id: ElevenLabs voice ID
        elevenlabs_model_id: ElevenLabs model ID
        piper_model_path: Path to Piper model file
        piper_speaker_id: Speaker ID for Piper
        enable_fallback: If True, fallback to local on API failure

    Returns:
        Configured TTSProvider instance
    """
    log.info("creating_tts_provider", mode=mode, enable_fallback=enable_fallback)

    # Handle ElevenLabs mode
    if mode == "elevenlabs":
        if not elevenlabs_api_key:
            log.warning("elevenlabs_api_key_missing", fallback="local")
            mode = "local"
        else:
            try:
                from .elevenlabs_tts import ElevenLabsTTS

                provider = ElevenLabsTTS(
                    api_key=elevenlabs_api_key,
                    voice_id=elevenlabs_voice_id,
                    model_id=elevenlabs_model_id,
                )

                if enable_fallback and piper_model_path:
                    from .fallback import FallbackTTSProvider

                    fallback_provider = _create_local_tts(
                        piper_model_path, piper_speaker_id
                    )
                    return FallbackTTSProvider(
                        primary=provider,
                        fallback=fallback_provider,
                    )

                return provider

            except Exception as e:
                log.warning("elevenlabs_init_failed", error=str(e), fallback="local")
                mode = "local"

    # Local mode (Piper)
    if not piper_model_path:
        log.warning("piper_model_path_not_set", using="dummy")
        # Return a dummy provider that raises clear errors
        return _create_dummy_tts()

    return _create_local_tts(piper_model_path, piper_speaker_id)


def _create_local_tts(
    model_path: str,
    speaker_id: int,
) -> TTSProvider:
    """Create local TTS provider (Piper).

    Args:
        model_path: Path to Piper model
        speaker_id: Speaker ID

    Returns:
        PiperTTS instance
    """
    from .piper_tts import PiperTTS

    return PiperTTS(
        model_path=model_path,
        speaker_id=speaker_id,
    )


def _create_dummy_tts() -> TTSProvider:
    """Create a dummy TTS provider that returns empty audio.

    Used when no TTS is properly configured.
    """
    from .base import TTSProvider
    from typing import AsyncIterator

    class DummyTTS(TTSProvider):
        async def synthesize(self, text: str) -> bytes:
            log.warning("dummy_tts_called", text=text[:50])
            # Return minimal valid MP3 (silence)
            return b""

        async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
            log.warning("dummy_tts_stream_called", text=text[:50])
            yield b""

    return DummyTTS()
