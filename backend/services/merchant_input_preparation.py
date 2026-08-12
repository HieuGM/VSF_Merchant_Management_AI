"""Tool-less small-model preparation of one merchant chat request."""
from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from pydantic import ValidationError

from agents.merchant.input_analyzer_prompt import (
    TRUNCATION_MARKER,
    build_bounded_prompt,
    build_repair_prompt,
    redact_sensitive_content,
    redact_sensitive_text,
)
from models.merchant_input import PreparedRequest


TraceCallback = Callable[[str, dict[str, Any]], None]
TRACE_PROMPT_LIMIT = 5_000
TRACE_MODEL_ARTIFACT_LIMIT = 3_000


class InputAnalyzerLLM(Protocol):
    """The narrow CrewAI-compatible seam used by this service."""

    def call(self, prompt: str) -> str | Any:
        """Return the provider response for one prompt."""


class InputPreparationError(RuntimeError):
    """Stable, safe errors for deterministic routing to handle."""


class InputPreparationService:
    """Prepare a strict request contract without tools or orchestration logic.

    The caller owns construction of the small model (normally
    ``get_configured_llm("small")``) and injects it here. This prevents this
    layer from configuring providers or accidentally calling one in tests.
    """

    def __init__(
        self,
        *,
        llm: InputAnalyzerLLM,
        trace_callback: TraceCallback | None = None,
    ) -> None:
        self._llm = llm
        self._trace_callback = trace_callback

    def prepare(
        self,
        *,
        raw_query: str,
        history: list[dict[str, Any]],
        session_state: dict[str, Any],
        owner_context: dict[str, Any],
    ) -> PreparedRequest:
        """Call the analyzer once, with exactly one schema-repair attempt."""
        started_at = time.perf_counter()
        prompt = build_bounded_prompt(
            raw_query=raw_query,
            history=history,
            session_state=session_state,
            owner_context=owner_context,
        )
        raw_output = ""
        repair_prompt: str | None = None
        repair_output: str | None = None
        usages: list[dict[str, int]] = []
        parse_result = "provider_call_failed"
        parsed_request: PreparedRequest | None = None

        try:
            raw_output, usage = self._call(prompt)
            if usage is not None:
                usages.append(usage)
            try:
                parsed_request = _parse_prepared_request(raw_output)
                parse_result = "ok"
                return parsed_request
            except (ValidationError, ValueError):
                repair_prompt = build_repair_prompt(raw_output)
                repair_output, usage = self._call(repair_prompt)
                if usage is not None:
                    usages.append(usage)
                try:
                    parsed_request = _parse_prepared_request(repair_output)
                    parse_result = "repaired"
                    return parsed_request
                except (ValidationError, ValueError) as error:
                    parse_result = "schema_repair_failed"
                    raise InputPreparationError("schema_repair_failed") from error
        except InputPreparationError:
            raise
        except Exception as error:
            raise InputPreparationError("provider_call_failed") from error
        finally:
            self._emit_trace(
                raw_prompt=prompt,
                raw_output=raw_output,
                repair_output=repair_output,
                parse_result=parse_result,
                parsed_request=parsed_request,
                duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
                token_usage=_sum_usage(usages),
            )

    def _call(self, prompt: str) -> tuple[str, dict[str, int] | None]:
        response = self._llm.call(prompt)
        return _response_text(response), _response_usage(response)

    def _emit_trace(
        self,
        *,
        raw_prompt: str,
        raw_output: str,
        repair_output: str | None,
        parse_result: str,
        parsed_request: PreparedRequest | None,
        duration_ms: float,
        token_usage: dict[str, int] | None,
    ) -> None:
        if self._trace_callback is None:
            return
        payload: dict[str, Any] = {
            # The prompt is the exact, already-bounded provider input. Do not
            # pass it through RequestTelemetry's unrelated 1,500-char string cap.
            "raw_prompt": _trace_text(raw_prompt, TRACE_PROMPT_LIMIT),
            "raw_model_output": _trace_text(raw_output, TRACE_MODEL_ARTIFACT_LIMIT),
            "repair_model_output": (
                _trace_text(repair_output, TRACE_MODEL_ARTIFACT_LIMIT)
                if repair_output is not None
                else None
            ),
            "parse_result": parse_result,
            "parsed_request": _trace_value(parsed_request.model_dump())
            if parsed_request
            else None,
            "duration_ms": duration_ms,
            "token_usage": token_usage,
            "hidden_reasoning": "not_available",
        }
        try:
            self._trace_callback("input_analyzer", payload)
        except Exception:
            # Observability must not turn a valid chat request into a failure.
            return


def _response_text(response: str | Any) -> str:
    if isinstance(response, str):
        return response
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(response, Mapping):
        candidate = response.get("content", response.get("text", response))
        if isinstance(candidate, str):
            return candidate
        return json.dumps(candidate, ensure_ascii=False, default=str)
    return str(response)


def _parse_prepared_request(raw_output: str) -> PreparedRequest:
    """Parse bounded provider JSON while repairing known transport-level quirks.

    Gemini-compatible endpoints sometimes escape apostrophes as ``\'``, which
    JSON does not permit, or return the concise aliases used in repair prompts.
    This normalizes only those representation defects; Pydantic still enforces
    the complete request contract and rejects unknown fields.
    """
    normalized = raw_output.strip().replace("\\'", "'")
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        normalized = "\n".join(lines).strip()
    payload = json.loads(normalized)
    if not isinstance(payload, dict):
        raise ValueError("Input Analyzer output must be a JSON object")
    canonical = dict(payload)
    if "scope_candidate" not in canonical and "scope" in canonical:
        canonical["scope_candidate"] = canonical.pop("scope")
    if "proposed_outcome" not in canonical and "outcome" in canonical:
        canonical["proposed_outcome"] = canonical.pop("outcome")
    return PreparedRequest.model_validate(canonical)


def _response_usage(response: Any) -> dict[str, int] | None:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, Mapping):
        usage = response.get("usage")
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    if not isinstance(usage, Mapping):
        return None
    normalized = {
        "prompt_tokens": _usage_int(usage, "prompt_tokens", "input_tokens"),
        "completion_tokens": _usage_int(usage, "completion_tokens", "output_tokens"),
        "total_tokens": _usage_int(usage, "total_tokens"),
    }
    if not any(normalized.values()):
        return None
    if not normalized["total_tokens"]:
        normalized["total_tokens"] = (
            normalized["prompt_tokens"] + normalized["completion_tokens"]
        )
    return normalized


def _usage_int(usage: Mapping[str, Any], *keys: str) -> int:
    for key in keys:
        value = usage.get(key)
        if isinstance(value, (int, float)):
            return max(0, int(value))
    return 0


def _sum_usage(usages: list[dict[str, int]]) -> dict[str, int] | None:
    if not usages:
        return None
    return {
        key: sum(usage[key] for usage in usages)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }


def _trace_value(value: Any) -> Any:
    """Keep actual raw artifacts developer-visible but redacted and bounded."""
    return redact_sensitive_content(value)


def _trace_text(value: str, limit: int) -> str:
    """Preserve complete bounded prompts while capping other raw text safely."""
    sanitized = redact_sensitive_text(value)
    if len(sanitized) <= limit:
        return sanitized
    return sanitized[: max(0, limit - len(TRUNCATION_MARKER))] + TRUNCATION_MARKER
