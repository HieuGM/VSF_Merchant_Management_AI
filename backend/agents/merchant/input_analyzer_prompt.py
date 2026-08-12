"""Bounded prompt construction for merchant request preparation via remote Langfuse Prompt Management."""
from __future__ import annotations

import json
import re
from typing import Any
from models.merchant_input import PromptBudget
from services.merchant_prompts import compile_merchant_prompt


INPUT_ANALYZER_BUDGET = PromptBudget(
    dynamic_input_limit=1_600,
    output_limit=300,
)

RAW_QUERY_LIMIT = 600
HISTORY_LIMIT = 1_200
SESSION_CONTEXT_LIMIT = 500
OWNER_CONTEXT_LIMIT = 300
TRUNCATION_MARKER = "\n<truncated>"

_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?P<key>api[_-]?key|authorization|password|secret|access[_-]?token|refresh[_-]?token)"
    r"(?P<separator>\s*[:=]\s*)"
    r"(?P<value>\"[^\"]*\"|'[^']*'|[^\s,;]+)",
    re.IGNORECASE,
)
_QUOTED_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?P<quote>[\"'])(?P<key>api[_-]?key|authorization|password|secret|access[_-]?token|refresh[_-]?token)(?P=quote)"
    r"(?P<separator>\s*:\s*)"
    r"(?P<value>\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'|[^\s,;}]+)",
    re.IGNORECASE,
)
_BEARER_TOKEN = re.compile(r"\bBearer\s+[^\s,;]+", re.IGNORECASE)
_OPENAI_STYLE_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")


def compile_bounded_prompt(
    *,
    raw_query: str,
    history: list[dict[str, Any]],
    session_state: dict[str, Any],
    owner_context: dict[str, Any],
) -> tuple[str, Any]:
    """Build the complete analyzer prompt with redacted, explicit bounds."""
    recent_history = history[-3:]
    return compile_merchant_prompt(
        "INPUT_ANALYZER_PROMPT",
        raw_user_query=_bounded_serialized(raw_query, RAW_QUERY_LIMIT),
        recent_history=_bounded_serialized(recent_history, HISTORY_LIMIT),
        session_context=_bounded_serialized(session_state, SESSION_CONTEXT_LIMIT),
        owner_context=_bounded_serialized(owner_context, OWNER_CONTEXT_LIMIT),
    )


def build_bounded_prompt(**kwargs: Any) -> str:
    return compile_bounded_prompt(**kwargs)[0]


def _section(name: str, value: Any, limit: int) -> str:
    return f"[{name}]\n{_bounded_serialized(value, limit)}\n[/{name}]"


def _bounded_serialized(value: Any, limit: int) -> str:
    """Serialize dynamic data safely, marking every application truncation."""
    sanitized = redact_sensitive_content(value)
    if isinstance(sanitized, str):
        serialized = sanitized
    else:
        serialized = json.dumps(
            sanitized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    if len(serialized) <= limit:
        return serialized
    return serialized[: max(0, limit - len(TRUNCATION_MARKER))] + TRUNCATION_MARKER


def redact_sensitive_content(value: Any) -> Any:
    """Redact sensitive keyed fields and secret-looking values in all text."""
    return _redact_strings(_redact_sensitive_keys(value))


def _redact_sensitive_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "<redacted>" if re.search(r"api.?key|authorization|password|secret|token", str(key), re.I)
            else _redact_sensitive_keys(nested)
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [_redact_sensitive_keys(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_sensitive_keys(item) for item in value)
    return value


def redact_sensitive_text(text: str) -> str:
    """Redact common secret forms that occur inside arbitrary user text."""
    text = _QUOTED_SENSITIVE_ASSIGNMENT.sub(
        lambda match: (
            f"{match.group('quote')}{match.group('key')}{match.group('quote')}"
            f"{match.group('separator')}\"<redacted>\""
        ),
        text,
    )
    text = _SENSITIVE_ASSIGNMENT.sub(
        lambda match: f"{match.group('key')}{match.group('separator')}<redacted>",
        text,
    )
    text = _BEARER_TOKEN.sub("Bearer <redacted>", text)
    return _OPENAI_STYLE_KEY.sub("<redacted>", text)


def _redact_strings(value: Any) -> Any:
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, dict):
        return {key: _redact_strings(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [_redact_strings(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_strings(item) for item in value)
    return value
