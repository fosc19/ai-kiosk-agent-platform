from typing import Literal, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 9001
    log_level: str = "INFO"

    # Audio validation settings
    expected_sample_rate: int = 16000
    expected_channels: int = 1

    # Debug settings
    debug_save_audio: bool = False
    audio_save_path: str = "/tmp/audio_debug"

    # VAD settings (Silero) - Adjusted for faster detection
    vad_threshold: float = 0.4  # Lower threshold for easier speech detection
    vad_min_speech_ms: int = 250  # Minimum speech duration to register
    vad_min_silence_ms: int = 500  # Shorter silence needed to end speech (faster response)

    # === Mode selection ===
    asr_mode: Literal["local", "deepgram"] = "local"
    tts_mode: Literal["local", "elevenlabs"] = "local"

    # ASR settings (Deepgram - premium)
    deepgram_api_key: Optional[str] = None
    asr_language: str = "es"
    asr_model: str = "nova-2"

    # ASR settings (faster-whisper - local)
    whisper_model_size: str = "tiny"  # tiny is faster for real-time (small, medium, large-v2)
    whisper_device: str = "auto"  # auto, cpu, cuda
    whisper_compute_type: str = "int8"  # int8 is faster on CPU (auto, int8, float16, float32)
    whisper_prompt: str = "Demo Fashion, Coffee Point, Urban Wear, tienda, centro comercial"  # Vocabulary hint

    # TTS settings (ElevenLabs - premium)
    elevenlabs_api_key: Optional[str] = None
    tts_voice_id: str = "pNInz6obpgDQGcFmaJgB"  # Spanish female
    tts_model_id: str = "eleven_multilingual_v2"

    # TTS settings (Piper - local)
    piper_model_path: Optional[str] = None
    piper_speaker_id: int = 0

    # TTS Cache settings
    tts_cache_enabled: bool = True
    tts_cache_dir: str = "/tmp/tts_cache"
    tts_cache_preload: bool = True

    # Fallback settings
    enable_fallback: bool = True  # Fallback to local on API failure

    model_config = {
        "env_prefix": "SPEECH_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
