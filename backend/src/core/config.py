"""Application configuration powered by pydantic-settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Typed environment settings for bravo-erp backend and workers."""

    model_config = SettingsConfigDict(
        env_file=(str(_ROOT_ENV_PATH), ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    app_name: str = "bravo-erp"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    # PostgreSQL 17 Async Database
    postgres_user: str = "bravo"
    postgres_password: str = "bravo_dev_secret"
    postgres_db: str = "bravo_erp"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    database_url: str = "postgresql+asyncpg://bravo:bravo_dev_secret@localhost:5432/bravo_erp"

    # Redis 7 (Taskiq Broker & Result Backend)
    redis_url: str = "redis://localhost:6379/0"

    # MinIO / S3 Object Storage
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin_secret"
    minio_bucket_name: str = "bravo-erp"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_public_endpoint_url: str = "http://localhost:9000"
    s3_region: str = "us-east-1"

    # JWT & Auth Security
    jwt_secret_key: str = "bravo-erp-dev-super-secret-jwt-key-change-in-prod-2026"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 480


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton application settings."""
    return Settings()
