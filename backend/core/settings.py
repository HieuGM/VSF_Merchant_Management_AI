"""Application settings — single source of truth for runtime config.

FROZEN SEAM (Phase 0): both Customer (Dev A) and Merchant (Dev B) verticals read
config from here. Add new fields, do not rename/remove existing ones without going
through the contract-change protocol (plan.md §[C2]).
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Load env from repo root first, then backend/.env (later file wins). Paths are resolved
# from this file so config loads regardless of the process CWD.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
_ROOT_DIR = _BACKEND_DIR.parent


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

    # --- LLM (CrewAI 1.15.5) ---
    # NVIDIA NIM, per-agent 2-tier (plan decision §3). NIM is OpenAI-compatible, so we use
    # CrewAI's native `openai` provider pointed at the NIM endpoint — this avoids pulling in
    # litellm (which conflicts with crewai's openai>=2.30 pin) while keeping the same decided
    # outcome (NVIDIA NIM models, NVIDIA_NIM_API_KEY). Legacy llm_api_key/llm_model kept so
    # the frozen seam does not break. Additive-only edit (contract-safe).
    llm_provider: str = "openai"  # native provider talking to the OpenAI-compatible NIM API
    llm_api_key: str | None = None  # legacy seam (do not remove)
    llm_model: str = "gpt-4o-mini"  # legacy seam (do not remove)
    nvidia_nim_api_key: str | None = None  # from NVIDIA_NIM_API_KEY
    llm_model_large: str = "meta/llama-3.3-70b-instruct"
    llm_model_small: str = "meta/llama-3.1-8b-instruct"
    # Default NIM hosted endpoint; override via LLM_BASE_URL for self-hosted NIM.
    llm_base_url: str = "https://integrate.api.nvidia.com/v1"

    # --- FPT Cloud AI (OpenAI-compatible; DeepSeek/Qwen). Much lower latency than the NIM
    # free tier. When these are set, the crew auto-selects FPT unless LLM_VENDOR forces a
    # vendor. All are read from the corresponding UPPER_CASE env vars. ---
    fpt_api_key: str | None = None            # FPT_API_KEY
    fpt_base_url: str | None = None           # FPT_BASE_URL
    fpt_model_deepseek: str | None = None     # FPT_MODEL_DEEPSEEK
    fpt_model_qwen: str | None = None         # FPT_MODEL_QWEN
    # Primary model for customer agents. gpt-oss-20b is the fastest tool-caller on FPT
    # (~0.69s/call vs DeepSeek-V4-Flash 1.25s) and holds Vietnamese NLG + anti-hallucination
    # quality, so the crew runs ~2x faster end-to-end. Override via FPT_MODEL_FAST if needed.
    fpt_model_fast: str = "gpt-oss-20b"       # FPT_MODEL_FAST
    # Explicit vendor override: "fpt" | "nvidia_nim". Empty = auto-detect.
    llm_vendor: str = ""

    # --- Cache ---
    cache_backend: str = "memory"  # "memory" | "redis"

    # --- Profile-based ranking (phase-02). Additive taste-profile boost/hard-filter on
    # merchant search. Default enabled but no-profile = no-op (behavior unchanged). Flip
    # ranking_enabled=False to kill-switch. Weights are small (nudge, not dominate) the
    # relevance scoring in docs/scoring-methodology.md. ---
    ranking_enabled: bool = True
    ranking_w_budget: float = 0.06
    ranking_w_liked: float = 0.03
    ranking_liked_cap: int = 2
    ranking_w_disliked: float = 0.05
    ranking_w_dietary: float = 0.04
    ranking_hard_filter_disliked: bool = False

    # --- CORS (FE origins) — comma-separated. Default is the Vite dev server only;
    # do NOT use "*" together with credentials (reflects any origin). ---
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = SettingsConfigDict(
        env_file=(str(_ROOT_DIR / ".env"), str(_BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.db_host}:{self.db_port}/{self.postgres_db}"
        )

    @property
    def fpt_configured(self) -> bool:
        """True when FPT Cloud AI (DeepSeek) is fully configured."""
        return bool(self.fpt_api_key and self.fpt_base_url and self.fpt_model_deepseek)

    @property
    def active_llm_vendor(self) -> str:
        """Selected LLM vendor: explicit LLM_VENDOR override, else auto-detect.

        Auto: prefer FPT (fast) when configured, otherwise NVIDIA NIM."""
        if self.llm_vendor:
            return self.llm_vendor.strip().lower()
        return "fpt" if self.fpt_configured else "nvidia_nim"

    @property
    def llm_configured(self) -> bool:
        """True when the crew can run live with the active vendor's credentials."""
        if self.active_llm_vendor == "fpt":
            return self.fpt_configured
        return bool(self.nvidia_nim_api_key)


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so config is parsed once per process."""
    return Settings()
