from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 9003
    log_level: str = "INFO"

    # MediaPipe settings
    min_detection_confidence: float = 0.7

    model_config = {"env_prefix": "VISION_"}


settings = Settings()
