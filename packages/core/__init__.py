"""Core application settings loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide configuration via pydantic-settings / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://fnews:changeme@localhost:5432/fnews"

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Email – outbound ──────────────────────────────────────────────────────
    email_smtp_host: str = "smtp.example.com"
    email_smtp_port: int = 587
    email_smtp_user: str = "you@example.com"
    email_smtp_pass: str = ""
    email_from: str = "fnews@example.com"
    email_to: str = "you@example.com"

    # ── Email – inbound ───────────────────────────────────────────────────────
    email_imap_host: str = "imap.example.com"
    email_imap_port: int = 993
    email_imap_user: str = "you@example.com"
    email_imap_pass: str = ""

    # ── LLM ───────────────────────────────────────────────────────────────────
    llm_backend: str = "ollama"  # ollama | vllm | llamacpp
    llm_base_url: str = "http://localhost:11434"
    llm_model_name: str = "llama3"

    # ── Embeddings ────────────────────────────────────────────────────────────
    embedding_model_name: str = "BAAI/bge-small-en-v1.5"

    # ── Alerts ────────────────────────────────────────────────────────────────
    alert_threshold: int = 70
    alert_min_sources: int = 2

    # ── Source / watchlist config ─────────────────────────────────────────────
    source_config_path: str = "/app/config/sources.yaml"
    watchlist_config_path: str = "/app/config/watchlist.yaml"

    # ── API auth ──────────────────────────────────────────────────────────────
    api_key: str = "changeme-api-key-here"

    # ── Scheduling ────────────────────────────────────────────────────────────
    briefing_cron: str = "0 7 * * *"
    ingestion_interval_minutes: int = 30

    # ── Blob storage ──────────────────────────────────────────────────────────
    blob_store_path: str = "/data/blobs"

    # ── Chunking ──────────────────────────────────────────────────────────────
    chunk_size: int = 512
    chunk_overlap: int = 64

    # ── Self-evaluation ───────────────────────────────────────────────────────
    eval_window_days: int = 7

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"

    @field_validator("llm_backend")
    @classmethod
    def validate_backend(cls, v: str) -> str:
        allowed = {"ollama", "vllm", "llamacpp"}
        if v not in allowed:
            raise ValueError(f"llm_backend must be one of {allowed}")
        return v

    @property
    def sync_database_url(self) -> str:
        """Synchronous database URL for Alembic / non-async contexts."""
        return self.database_url.replace("+asyncpg", "+psycopg2")

    @property
    def blob_store_path_obj(self) -> Path:
        return Path(self.blob_store_path)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton settings instance."""
    return Settings()
