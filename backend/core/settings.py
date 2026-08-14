"""Application settings — single source of truth for runtime config.

FROZEN SEAM (Phase 0): both Customer (Dev A) and Merchant (Dev B) verticals read
config from here. Add new fields, do not rename/remove existing ones without going
through the contract-change protocol (plan.md §[C2]).
"""
from typing import Literal

from functools import lru_cache
from dotenv import find_dotenv, load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Automatically find and load .env from project root or parent directories
load_dotenv(find_dotenv(usecwd=True), override=False)


class Settings(BaseSettings):
    # --- App ---
    app_name: str = "VSF Merchant AI"
    api_v1_prefix: str = "/api/v1"
    environment: str = "development"

    # --- Postgres ---
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "merchant_platform"
    db_host: str = "localhost"
    db_port: str = "5432"

    # --- Redis (Feature D-02; optional at Phase 0 — memory adapter is default) ---
    redis_url: str | None = None

    # --- LLM (CrewAI 1.15.5 Model Tiering) ---
    llm_provider: str = "openai"
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_model_small: str | None = None  # Model nhỏ / fast (Intent, Scope Guard, etc.)
    llm_model_large: str | None = None  # Model lớn / heavy (Synthesis, Audit, Diagnosis)
    llm_base_url: str | None = None

    # --- Execution Mode ---
    merchant_execution_mode: Literal["legacy", "shadow", "active"] = "legacy"

    # --- Policy RAG ---
    rag_embedding_api_key: str | None = None
    rag_embedding_base_url: str | None = None
    rag_embedding_model: str = "BAAI/bge-small-en-v1.5"
    rag_embedding_dimensions: int = 384
    rag_chroma_path: str = ".runtime/policy-rag"
    rag_collection: str = "green-sm-policy"
    rag_score_threshold: float = 0.6

    # Langfuse 
    langfuse_secret_key: str = ""
    langfuse_public_key: str = ""
    langfuse_base_url: str = ""
    langfuse_prompt_label: str = "production"
    langfuse_prompt_cache_ttl_seconds: int = 60

    # --- Cache ---
    cache_backend: str = "redis"  # "memory" | "redis"

    # --- CORS (FE origins) — comma-separated. Default is the Vite dev server only;
    # do NOT use "*" together with credentials (reflects any origin). ---
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.db_host}:{self.db_port}/{self.postgres_db}"
        )

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key)

    @property
    def policy_rag_configured(self) -> bool:
        return True


def sync_langfuse_env(settings: Settings) -> None:
    """Export Langfuse settings to os.environ for OpenTelemetry & Langfuse SDK."""
    import os

    if settings.langfuse_secret_key:
        os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key
    if settings.langfuse_public_key:
        os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
    if settings.langfuse_base_url:
        os.environ["LANGFUSE_BASE_URL"] = settings.langfuse_base_url
    os.environ["LANGFUSE_TRACING_ENVIRONMENT"] = settings.environment


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so config is parsed once per process."""
    s = Settings()
    sync_langfuse_env(s)
    return s
