"""Factory for creating ASR providers."""

from __future__ import annotations

from typing import Literal, Optional

import structlog

from .base import ASRProvider

log = structlog.get_logger()

ASRMode = Literal["local", "deepgram"]


def create_asr_provider(
    mode: ASRMode,
    *,
    language: str = "es",
    # Deepgram config
    deepgram_api_key: Optional[str] = None,
    deepgram_model: str = "nova-2",
    # Local config
    whisper_model_size: str = "small",
    whisper_device: str = "auto",
    whisper_compute_type: str = "auto",
    whisper_prompt: str = "",
    # Fallback
    enable_fallback: bool = True,
) -> ASRProvider:
    """Create ASR provider based on mode.

    Args:
        mode: "local" for faster-whisper, "deepgram" for API
        language: Language code (default: "es")
        deepgram_api_key: API key for Deepgram
        deepgram_model: Deepgram model name
        whisper_model_size: Whisper model size (small/medium/large-v2)
        whisper_device: Device for whisper (auto/cpu/cuda)
        whisper_compute_type: Compute type (auto/int8/float16/float32)
        whisper_prompt: Initial prompt with vocabulary hints (e.g., store names)
        enable_fallback: If True, fallback to local on API failure

    Returns:
        Configured ASRProvider instance
    """
    log.info("creating_asr_provider", mode=mode, enable_fallback=enable_fallback)

    # Handle Deepgram mode
    if mode == "deepgram":
        if not deepgram_api_key:
            log.warning("deepgram_api_key_missing", fallback="local")
            mode = "local"
        else:
            try:
                from .deepgram_asr import DeepgramASR

                provider = DeepgramASR(
                    api_key=deepgram_api_key,
                    language=language,
                    model=deepgram_model,
                )

                if enable_fallback:
                    from .fallback import FallbackASRProvider

                    fallback_provider = _create_local_asr(
                        language, whisper_model_size, whisper_device, whisper_compute_type, whisper_prompt
                    )
                    return FallbackASRProvider(
                        primary=provider,
                        fallback=fallback_provider,
                    )

                return provider

            except Exception as e:
                log.warning("deepgram_init_failed", error=str(e), fallback="local")
                mode = "local"

    # Local mode (faster-whisper)
    return _create_local_asr(
        language, whisper_model_size, whisper_device, whisper_compute_type, whisper_prompt
    )


def _create_local_asr(
    language: str,
    model_size: str,
    device: str,
    compute_type: str,
    prompt: str = "",
) -> ASRProvider:
    """Create local ASR provider (faster-whisper).

    Args:
        language: Language code
        model_size: Whisper model size
        device: Device to use
        compute_type: Compute type
        prompt: Initial prompt with vocabulary hints

    Returns:
        FasterWhisperASR instance
    """
    from .faster_whisper_asr import FasterWhisperASR

    return FasterWhisperASR(
        model_size=model_size,
        language=language,
        device=device,
        compute_type=compute_type,
        prompt=prompt,
    )
