"""Sanitized trace envelopes for the developer monitoring dashboard."""
from __future__ import annotations

import time
from contextlib import contextmanager
from math import ceil
from typing import Any, Callable, Iterator, Iterable

from sqlalchemy import event
from sqlalchemy.orm import Session


class RequestTelemetry:
    """Aggregate persisted native events without reconstructing HTTP logs."""

    _SENSITIVE_KEY_PARTS = ("api_key", "authorization", "password", "secret", "access_token", "refresh_token")
    _MAX_DEPTH = 5
    _MAX_ITEMS = 30
    _MAX_TEXT = 1_500

    @classmethod
    def sanitize(cls, value: Any, depth: int = 0) -> Any:
        """Keep trace payloads inspectable while bounding unsafe/large fields."""
        if depth >= cls._MAX_DEPTH:
            return "<truncated>"
        if isinstance(value, dict):
            sanitized: dict[str, Any] = {}
            for key, nested in list(value.items())[: cls._MAX_ITEMS]:
                lowered = str(key).casefold()
                sanitized[str(key)] = (
                    "<redacted>"
                    if any(part in lowered for part in cls._SENSITIVE_KEY_PARTS)
                    else cls.sanitize(nested, depth + 1)
                )
            if len(value) > cls._MAX_ITEMS:
                sanitized["_truncated_items"] = len(value) - cls._MAX_ITEMS
            return sanitized
        if isinstance(value, (list, tuple)):
            items = [cls.sanitize(item, depth + 1) for item in value[: cls._MAX_ITEMS]]
            if len(value) > cls._MAX_ITEMS:
                items.append({"_truncated_items": len(value) - cls._MAX_ITEMS})
            return items
        if isinstance(value, str) and len(value) > cls._MAX_TEXT:
            return value[: cls._MAX_TEXT] + "…"
        return value

    @classmethod
    def persistable_payload(cls, payload: dict[str, Any]) -> dict[str, Any]:
        """Sanitize a native CrewAI/gateway payload before durable persistence."""
        return cls.sanitize(
            {key: value for key, value in payload.items() if key != "timestamp"}
        )

    @classmethod
    def build_envelope(
        cls,
        *,
        trace_id: str,
        status: str,
        run_token_usage: dict[str, Any] | None,
        events: Iterable[dict[str, Any]],
        session_state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        normalized_events = [
            {
                **event,
                "output_summary": cls.sanitize(event.get("output_summary") or {}),
            }
            for event in events
        ]
        cache_events = [
            event["output_summary"]
            for event in normalized_events
            if event.get("event_type") == "cache"
        ]
        sql_queries = [
            {
                **event["output_summary"],
                "duration_ms": event.get("duration_ms"),
                "status": event.get("status"),
            }
            for event in normalized_events
            if event.get("event_type") == "sql_query"
        ]
        span_usage = cls._sum_span_usage(normalized_events)
        llm_usage = span_usage if span_usage["total_tokens"] else cls._usage(run_token_usage)
        durations = [
            float(event["duration_ms"])
            for event in normalized_events
            if isinstance(event.get("duration_ms"), (int, float))
        ]

        return {
            "trace_id": trace_id,
            "status": status,
            "summary": {
                "event_count": len(normalized_events),
                "error_count": sum(
                    1
                    for event in normalized_events
                    if event.get("status") in {"error", "failed"}
                    or event.get("event_type") == "error"
                ),
                "cache_hit_count": sum(
                    1 for event in cache_events if event.get("status") == "hit"
                ),
                "cache_miss_count": sum(
                    1 for event in cache_events if event.get("status") == "miss"
                ),
            },
            "session_state": cls.sanitize(session_state or {}),
            "cache": cache_events,
            "sql_queries": sql_queries,
            "llm_usage": llm_usage,
            "performance": cls._performance(durations),
            "events": normalized_events,
        }

    @staticmethod
    def _usage(value: Any) -> dict[str, int | None]:
        usage = value if isinstance(value, dict) else {}
        return {
            "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
            "total_tokens": int(usage.get("total_tokens", 0) or 0),
            "estimated_cost_usd": None,
        }

    @classmethod
    def _sum_span_usage(cls, events: Iterable[dict[str, Any]]) -> dict[str, int | None]:
        prompt = completion = total = 0
        for event in events:
            if event.get("event_type") != "crewai_llm_finished":
                continue
            usage = cls._usage(event.get("output_summary", {}).get("token_usage"))
            prompt += int(usage["prompt_tokens"] or 0)
            completion += int(usage["completion_tokens"] or 0)
            total += int(usage["total_tokens"] or 0)
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
            "estimated_cost_usd": None,
        }

    @staticmethod
    def _performance(durations: list[float]) -> dict[str, float | None]:
        if not durations:
            return {"count": 0, "average_ms": None, "p95_ms": None, "p99_ms": None}
        ordered = sorted(durations)
        percentile = lambda fraction: ordered[min(len(ordered) - 1, ceil(len(ordered) * fraction) - 1)]
        return {
            "count": len(ordered),
            "average_ms": round(sum(ordered) / len(ordered), 3),
            "p95_ms": percentile(0.95),
            "p99_ms": percentile(0.99),
        }


class SqlQueryMonitor:
    """Temporarily observe SQL for one request session without bind values."""

    def __init__(self, emit: Callable[[dict[str, Any]], None]) -> None:
        self._emit = emit

    @contextmanager
    def capture(self, session: Session) -> Iterator[None]:
        target = session.get_bind()

        def before_cursor_execute(
            _connection: Any,
            _cursor: Any,
            _statement: str,
            _parameters: Any,
            context: Any,
            _executemany: bool,
        ) -> None:
            context._merchant_monitor_started_at = time.perf_counter()

        def after_cursor_execute(
            _connection: Any,
            cursor: Any,
            statement: str,
            _parameters: Any,
            context: Any,
            _executemany: bool,
        ) -> None:
            started = getattr(context, "_merchant_monitor_started_at", None)
            row_count = getattr(cursor, "rowcount", None)
            self._emit(
                {
                    "statement": " ".join(statement.split())[:1_500],
                    "duration_ms": round(
                        (time.perf_counter() - started) * 1000, 3
                    )
                    if started is not None
                    else None,
                    "row_count": row_count if isinstance(row_count, int) and row_count >= 0 else None,
                }
            )

        event.listen(target, "before_cursor_execute", before_cursor_execute)
        event.listen(target, "after_cursor_execute", after_cursor_execute)
        try:
            yield
        finally:
            event.remove(target, "before_cursor_execute", before_cursor_execute)
            event.remove(target, "after_cursor_execute", after_cursor_execute)
