"""Read-only access to versioned merchant prompts in Langfuse."""
from __future__ import annotations

from typing import Any
from langfuse import get_client

from core.settings import get_settings

PROMPT_NAMES: dict[str, str] = {
    "planner": "merchant/planner",
    "owner": "merchant/specialist-owner",
    "market": "merchant/specialist-market",
    "policy": "merchant/specialist-policy",
    "review": "merchant/specialist-review",
    "cohort": "merchant/specialist-cohort",
    "synthesis": "merchant/synthesis",
}


def get_merchant_prompt(key: str, *, label: str | None = None) -> Any:
    settings = get_settings()
    return get_client().get_prompt(
        PROMPT_NAMES[key],
        label=label or settings.langfuse_prompt_label,
        cache_ttl_seconds=settings.langfuse_prompt_cache_ttl_seconds,
    )


def compile_merchant_prompt(key: str, *, label: str | None = None, **variables: str) -> tuple[str, Any]:
    prompt = get_merchant_prompt(key, label=label)
    return prompt.compile(**variables), prompt
