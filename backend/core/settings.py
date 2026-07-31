"""Application settings — single source of truth for runtime config.

FROZEN SEAM (Phase 0): both Customer (Dev A) and Merchant (Dev B) verticals read
config from here. Add new fields, do not rename/remove existing ones without going
through the contract-change protocol (plan.md §[C2]).
"""
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

    # --- Cache ---
    cache_backend: str = "memory"  # "memory" | "redis"

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


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so config is parsed once per process."""
    return Settings()
