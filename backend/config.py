"""Application settings, loaded from environment / .env file."""

from __future__ import annotations

import secrets
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- LLM API keys ---
    anthropic_api_key: str = ""
    groq_api_key: str = ""
    openai_api_key: str = ""
    openrouter_api_key: str = ""
    gemini_api_key:str = ""

    # --- Database ---
    db_password: str = "docgen_pass_123"
    database_url: str = (
        "postgresql+asyncpg://docgen:docgen_pass_123@localhost:5433/docgen"
    )

    # --- Document paths ---
    generated_docs_path: str = "./generated_docs"
    max_reference_upload_bytes: int = 10 * 1024 * 1024
    max_device_document_upload_bytes: int = 50 * 1024 * 1024

    # --- Embedding ---
    embed_model: str = "BAAI/bge-base-en-v1.5"
    embed_dimension: int = 768

    # --- Auth ---
    secret_key: SecretStr = SecretStr("change-me-in-production")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # --- LLM provider ---
    llm_provider: str = "anthropic"

    anthropic_model: str = "claude-3-5-sonnet-20241022"
    groq_model: str = "llama-3.3-70b-versatile"
    openai_model: str = "gpt-4o-mini"
    ollama_model: str = "llama3.1"
    openrouter_model: str = "google/gemini-2.5-pro"
    gemini_model: str = "gemini-2.5-flash"
    

    ollama_url: str = "http://localhost:11434/v1"

    # --- CORS ---
    cors_origins: str = (
        "http://localhost:5173,"
        "http://localhost,"
        "http://127.0.0.1:5173,"
        "http://127.0.0.1"
    )

    # --- Rate limiting ---
    rate_limit_enabled: bool = False
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            o.strip()
            for o in self.cors_origins.split(",")
            if o.strip()
        ]

    @property
    def effective_secret_key(self) -> str:
        key = self.secret_key.get_secret_value()

        if not key or key == "change-me-in-production":
            key = secrets.token_urlsafe(32)

        return key

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        extra="ignore",
    )


settings = Settings()