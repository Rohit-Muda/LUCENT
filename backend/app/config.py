from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: SecretStr | None = None
    upload_dir: Path = Path("uploads")
    pdf_dir: Path = Path("generated_pdfs")
    frontend_url: str = "http://localhost:5173"
    max_upload_size_bytes: int = Field(default=25_000_000, gt=0)
    max_audio_duration_seconds: int = Field(default=3600, gt=0)
    groq_api_key: SecretStr | None = None
    groq_model: str = "whisper-large-v3-turbo"
    groq_max_audio_size_bytes: int = Field(default=25_000_000, gt=0)
    groq_timeout_seconds: float = Field(default=180.0, gt=0)
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_timeout_seconds: float = Field(default=120.0, gt=0)
    processing_job_lease_seconds: int = Field(default=300, gt=0)
    processing_job_max_stage_attempts: int = Field(default=3, gt=0)
    processing_job_max_manual_retries: int = Field(default=2, ge=0)
    processing_job_retry_backoff_seconds: int = Field(default=15, gt=0)
    processing_job_poll_interval_seconds: float = Field(default=2.0, gt=0)

    # Optional HTTP Basic Auth for public deployment
    require_auth: bool = False
    auth_username: SecretStr | None = None
    auth_password: SecretStr | None = None

    @property
    def cors_origins(self) -> list[str]:
        origins: list[str] = []
        for raw_origin in self.frontend_url.split(","):
            origin = raw_origin.strip().rstrip("/")
            if origin and origin != "*":
                origins.append(origin)
        return origins


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
