"""Read-only access to versioned merchant prompts in Langfuse."""
from __future__ import annotations

from typing import Any

from langfuse import get_client

from core.settings import get_settings

PROMPT_PREFIX = "gsm_merchant/"


def get_merchant_prompt(key: str) -> Any:
    settings = get_settings()
    return get_client().get_prompt(
        f"{PROMPT_PREFIX}{key}",
        label=settings.langfuse_prompt_label,
        cache_ttl_seconds=settings.langfuse_prompt_cache_ttl_seconds,
    )


def compile_merchant_prompt(key: str, **variables: str) -> tuple[str, Any]:
    prompt = get_merchant_prompt(key)
    return prompt.compile(**variables), prompt
