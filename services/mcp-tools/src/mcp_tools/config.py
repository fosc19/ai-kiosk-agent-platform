"""Configuration settings for MCP Tools server."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """MCP Tools configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="MCP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database - default to SQLite for local development
    # Set MCP_DATABASE_URL for PostgreSQL in production/Docker
    database_url: str = "sqlite:///data/kiosk.db"

    # Server
    host: str = "0.0.0.0"
    port: int = 9002
    transport: Literal["stdio", "http"] = "stdio"

    # Logging
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"

    # Search
    fuzzy_threshold: float = 0.6  # Minimum similarity for fuzzy search


settings = Settings()
