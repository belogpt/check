import os
from functools import lru_cache

from pydantic import BaseSettings, Field, HttpUrl


class Settings(BaseSettings):
    app_name: str = "Receipt Splitter"
    environment: str = Field("development", env="ENVIRONMENT")
    database_url: str = Field("postgresql+asyncpg://postgres:postgres@db:5432/postgres", env="DATABASE_URL")
    media_root: str = Field("media", env="MEDIA_ROOT")
    tesseract_cmd: str | None = Field(default=None, env="TESSERACT_CMD")
    allowed_origins: list[HttpUrl] = Field(default_factory=list, env="ALLOWED_ORIGINS")
    upload_max_mb: int = Field(20, env="UPLOAD_MAX_MB")
    gunicorn_workers: int = Field(3, env="GUNICORN_WORKERS")

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()

