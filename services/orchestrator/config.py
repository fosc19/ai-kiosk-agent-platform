from typing import List, Optional, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration for Orchestrator service"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Service Discovery
    redis_url: str = "redis://localhost:6379"
    postgres_url: str = "postgresql://kiosk:kiosk_dev_password@localhost:5432/kiosk"

    # Speech Service
    speech_service_url: str = "http://localhost:9001"

    # Vision Service
    vision_service_url: str = "http://localhost:9003"

    # MCP Tools
    mcp_tools_url: str = "http://localhost:9002"

    # LLM Config
    llm_mode: str = "mock"  # mock | gemini | grok | anthropic | ollama | openrouter
    llm_model: Optional[str] = None  # Model name (uses defaults per provider)
    llm_temperature: float = 0.3

    # API Keys (get free keys at the URLs below)
    gemini_api_key: Optional[str] = None    # https://aistudio.google.com
    grok_api_key: Optional[str] = None      # https://console.x.ai
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None  # https://openrouter.ai

    # Ollama (local LLM - no API key needed)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b-instruct"
    ollama_timeout: float = 30.0

    # Security
    allowed_kiosk_ids: Union[str, List[str]] = ["pi-kiosk-dev", "pi-kiosk-001", "pi-kiosk-002"]
    api_keys: Union[str, List[str]] = ["dev_local_key_change_me"]

    @field_validator("allowed_kiosk_ids", "api_keys", mode="after")
    @classmethod
    def parse_list_from_string(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(",")]
        return v

    # F6: Conversation Memory
    conversation_memory_ttl: int = 300  # 5 minutes
    conversation_max_turns: int = 10

    # F6: Barge-in Detection
    barge_in_min_duration_ms: int = 150  # Minimum speech to trigger barge-in
    barge_in_energy_threshold: float = 0.02

    # F6: Streaming TTS
    tts_streaming_enabled: bool = True
    tts_chunk_size_ms: int = 500  # Size of TTS chunks

    # Observability
    log_level: str = "INFO"
    debug_save_audio: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8765


settings = Settings()
