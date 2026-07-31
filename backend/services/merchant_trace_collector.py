"""Ordered, compact semantic trace events for one merchant chat run.

The collector deliberately records observable inputs and outputs only.  It is
not a reasoning recorder: when CrewAI does not expose a raw value we represent
that fact as ``not_available`` instead of trying to reconstruct it.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from typing import Any, Literal

from models.merchant_input import TraceSpan
from services.request_telemetry import RequestTelemetry


TracePhase = Literal["input", "route", "coordinator", "agent", "tool", "synthesis"]
TraceActor = Literal["system", "analyzer", "coordinator", "agent", "tool"]
TraceKind = Literal["started", "finished", "failed", "cancelled"]
TraceEmit = Callable[[dict[str, Any]], None]

# This is the sole debug-payload exception to the generic 1,500-character
# telemetry cap.  It is an already-bounded, explicitly redacted representation
# of the exact Coordinator prompt supplied to CrewAI—not a general raw-payload
# escape hatch for tools or model output.
COORDINATOR_INPUT_ARTIFACT_KEY = "coordinator_input_artifact"
_COORDINATOR_ARTIFACT_MAX_TEXT = 10_240
_COORDINATOR_ARTIFACT_MAX_DEPTH = 6
_COORDINATOR_ARTIFACT_MAX_ITEMS = 30

_STRING_SECRET = re.compile(
    r"(?i)(?<![?&])\b(authorization|api[_-]?key|password|secret|access[_-]?token|refresh[_-]?token|token)"
    r"\b\s*[:=]\s*(?:bearer\s+)?[^\r\n]+"
)
_BEARER_SECRET = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_QUERY_SECRET = re.compile(
    r"(?i)([?&](?:authorization|api[_-]?key|password|secret|access[_-]?token|refresh[_-]?token|token)=[^&#\s]*)"
)
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "authorization",
    "password",
    "secret",
    "access_token",
    "refresh_token",
    "token",
)


def sanitize_developer_trace(value: Any) -> Any:
    """Bound and redact every payload sent to developer trace consumers."""
    return _redact_trace_strings(RequestTelemetry.sanitize(value))


def _explicit_artifact_truncation(value: str, limit: int) -> str:
    """Bound preserved Coordinator text without an ambiguous bare ellipsis."""
    if len(value) <= limit:
        return value
    marker_template = "\n[truncated: kept {kept} of {total} chars]"
    marker = marker_template.format(kept=0, total=len(value))
    kept = max(0, limit - len(marker))
    return f"{value[:kept]}{marker_template.format(kept=kept, total=len(value))}"


def sanitize_coordinator_prompt_value(value: Any, depth: int = 0) -> Any:
    """Redact and explicitly bound one prepared-Coordinator prompt value.

    This helper is used before the coordinator sees history or owner context,
    and again inside the strictly allowlisted trace artifact below.
    """
    if depth >= _COORDINATOR_ARTIFACT_MAX_DEPTH:
        return f"[truncated: max depth {_COORDINATOR_ARTIFACT_MAX_DEPTH}]"
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        value = model_dump(mode="json")
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        entries = list(value.items())
        for key, item in entries[:_COORDINATOR_ARTIFACT_MAX_ITEMS]:
            normalized_key = str(key)
            lowered = normalized_key.casefold().replace("-", "_")
            sanitized[normalized_key] = (
                "<redacted>"
                if any(part in lowered for part in _SENSITIVE_KEY_PARTS)
                else sanitize_coordinator_prompt_value(item, depth + 1)
            )
        if len(entries) > _COORDINATOR_ARTIFACT_MAX_ITEMS:
            sanitized["_truncated_items"] = (
                f"[truncated: omitted {len(entries) - _COORDINATOR_ARTIFACT_MAX_ITEMS} items]"
            )
        return sanitized
    if isinstance(value, (list, tuple)):
        sanitized_items = [
            sanitize_coordinator_prompt_value(item, depth + 1)
            for item in value[:_COORDINATOR_ARTIFACT_MAX_ITEMS]
        ]
        if len(value) > _COORDINATOR_ARTIFACT_MAX_ITEMS:
            sanitized_items.append(
                {
                    "_truncated_items": (
                        "[truncated: omitted "
                        f"{len(value) - _COORDINATOR_ARTIFACT_MAX_ITEMS} items]"
                    )
                }
            )
        return sanitized_items
    if isinstance(value, str):
        redacted = _STRING_SECRET.sub(r"\1: <redacted>", value)
        redacted = _BEARER_SECRET.sub("Bearer <redacted>", redacted)
        redacted = _QUERY_SECRET.sub(
            lambda match: match.group(1).split("=")[0] + "=<redacted>",
            redacted,
        )
        return _explicit_artifact_truncation(redacted, _COORDINATOR_ARTIFACT_MAX_TEXT)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _explicit_artifact_truncation(str(value), _COORDINATOR_ARTIFACT_MAX_TEXT)


def sanitize_coordinator_input_artifact(value: Any) -> dict[str, Any]:
    """Preserve exactly the four declared Coordinator artifact fields.

    The elevated 10,240-character limit is intentionally unavailable to
    arbitrary debug data. Unknown root keys and unknown prepared-input keys
    are dropped; their original parent debug object still receives generic
    telemetry sanitization before this narrow replacement is installed.
    """
    if not isinstance(value, dict):
        return {}
    root_keys = (
        "dynamic_context",
        "prepared_inputs",
        "coordinator_goal_prompt",
        "advisory_task_prompt",
    )
    prepared_input_keys = (
        "rewritten_query",
        "resolved_references",
        "compact_history",
        "owner_context",
    )
    sanitized: dict[str, Any] = {}
    for key in root_keys:
        if key not in value:
            continue
        if key != "prepared_inputs":
            sanitized[key] = sanitize_coordinator_prompt_value(value[key])
            continue
        raw_inputs = value[key]
        if not isinstance(raw_inputs, dict):
            sanitized[key] = {}
            continue
        sanitized[key] = {
            input_key: sanitize_coordinator_prompt_value(raw_inputs[input_key])
            for input_key in prepared_input_keys
            if input_key in raw_inputs
        }
    return sanitized


def sanitize_trace_debug(value: dict[str, Any]) -> dict[str, Any]:
    """Apply generic trace safety, preserving only the allowlisted artifact."""
    sanitized = sanitize_developer_trace(value)
    artifact = value.get(COORDINATOR_INPUT_ARTIFACT_KEY)
    if artifact is not None:
        sanitized[COORDINATOR_INPUT_ARTIFACT_KEY] = sanitize_coordinator_input_artifact(
            artifact
        )
    return sanitized


def _redact_trace_strings(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): (
                "<redacted>"
                if any(
                    part in str(key).casefold().replace("-", "_")
                    for part in _SENSITIVE_KEY_PARTS
                )
                else _redact_trace_strings(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_trace_strings(item) for item in value]
    if isinstance(value, str):
        redacted = _STRING_SECRET.sub(r"\1: <redacted>", value)
        redacted = _BEARER_SECRET.sub("Bearer <redacted>", redacted)
        return _QUERY_SECRET.sub(lambda match: match.group(1).split("=")[0] + "=<redacted>", redacted)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _redact_trace_strings(model_dump())
    return RequestTelemetry.sanitize(str(value))


def canonical_trace_actor(actor_name: str | None) -> str:
    """Map native CrewAI roles to the capability names used by the gateway."""
    normalized = " ".join(str(actor_name or "unknown_agent").casefold().split())
    aliases = {
        "public market search specialist": "market_search",
        "public cohort analysis specialist": "cohort_analysis",
        "owner performance analysis specialist": "self_analysis",
        "evidence and policy verifier": "evidence_verifier",
        "merchant advisory coordinator": "coordinator",
        "merchant owner answer specialist": "answer_specialist",
    }
    return aliases.get(normalized, normalized.replace(" ", "_"))


@dataclass(frozen=True)
class GatewayToolInvocation:
    key: tuple[str, str, str]
    correlation_id: str | None


@dataclass(frozen=True)
class SdkToolResolution:
    state: Literal["pending", "gateway", "sdk_only", "ambiguous"]
    span_id: str | None = None
    ambiguous_ids: tuple[str, ...] = ()


@dataclass
class _GatewayToolRecord:
    key: tuple[str, str, str]
    span_id: str | None
    correlation_id: str | None
    created_at: float


class ToolCorrelationBridge:
    """Bounded, run-local SDK/gateway correlation that tolerates async order.

    CrewAI callbacks may be delivered after a gateway call finishes.  Gateway
    invocations are therefore remembered briefly and an SDK event can attach to
    the already-finished semantic span.  A match is accepted only when exact and
    unique; otherwise the SDK observation is explicitly terminal ``sdk_only``.
    """

    _MAX_RECORDS = 64
    _TTL_SECONDS = 60.0

    def __init__(self) -> None:
        self._lock = RLock()
        self._pending: dict[tuple[str, str, str], list[str]] = defaultdict(list)
        self._pending_created: dict[str, float] = {}
        self._records: list[_GatewayToolRecord] = []
        self._records_by_correlation: dict[str, _GatewayToolRecord] = {}
        self._sdk_only: dict[str, float] = {}

    def begin_gateway_call(
        self, agent_name: str | None, tool_name: str, args: Any
    ) -> GatewayToolInvocation:
        key = self._key(agent_name, tool_name, args)
        with self._lock:
            self._prune_locked()
            pending = self._pending.get(key, [])
            correlation_id = pending.pop() if len(pending) == 1 else None
            if correlation_id:
                self._pending_created.pop(correlation_id, None)
            if not pending:
                self._pending.pop(key, None)
            return GatewayToolInvocation(key=key, correlation_id=correlation_id)

    def register_gateway_span(
        self, invocation: GatewayToolInvocation, span_id: str | None
    ) -> None:
        with self._lock:
            self._prune_locked()
            record = _GatewayToolRecord(
                key=invocation.key,
                span_id=span_id,
                correlation_id=invocation.correlation_id,
                created_at=time.monotonic(),
            )
            self._records.append(record)
            if record.correlation_id:
                self._records_by_correlation[record.correlation_id] = record
            self._records = self._records[-self._MAX_RECORDS :]
            kept = {id(item) for item in self._records}
            self._records_by_correlation = {
                correlation_id: item
                for correlation_id, item in self._records_by_correlation.items()
                if id(item) in kept
            }

    def observe_sdk_event(
        self,
        agent_name: str | None,
        tool_name: str,
        args: Any,
        correlation_id: str | None,
        *,
        is_start: bool,
    ) -> SdkToolResolution:
        if not correlation_id:
            return SdkToolResolution("sdk_only")
        key = self._key(agent_name, tool_name, args)
        with self._lock:
            self._prune_locked()
            record = self._records_by_correlation.get(correlation_id)
            if record:
                return SdkToolResolution("gateway", span_id=record.span_id)
            if correlation_id in self._sdk_only:
                return SdkToolResolution("sdk_only")

            candidates = [
                record
                for record in self._records
                if record.key == key and record.correlation_id is None
            ]
            if len(candidates) == 1:
                record = candidates[0]
                record.correlation_id = correlation_id
                self._records_by_correlation[correlation_id] = record
                return SdkToolResolution("gateway", span_id=record.span_id)
            if any(correlation_id in pending for pending in self._pending.values()):
                return SdkToolResolution("pending")
            if not is_start:
                self._sdk_only[correlation_id] = time.monotonic()
                return SdkToolResolution("sdk_only")

            pending = self._pending[key]
            if correlation_id not in pending:
                pending.append(correlation_id)
                self._pending_created[correlation_id] = time.monotonic()
            if len(pending) > 1:
                ambiguous = tuple(pending)
                self._pending.pop(key, None)
                for item in ambiguous:
                    self._sdk_only[item] = time.monotonic()
                    self._pending_created.pop(item, None)
                return SdkToolResolution("ambiguous", ambiguous_ids=ambiguous)
            return SdkToolResolution("pending")

    def discard(self, correlation_id: str | None) -> None:
        if not correlation_id:
            return
        with self._lock:
            for key, pending in list(self._pending.items()):
                if correlation_id in pending:
                    pending.remove(correlation_id)
                    self._pending_created.pop(correlation_id, None)
                    if not pending:
                        self._pending.pop(key, None)
                    break

    def drain_pending(self) -> tuple[str, ...]:
        """Return unresolved SDK IDs when a run ends, leaving no live orphan."""
        with self._lock:
            self._prune_locked()
            pending = tuple(
                correlation_id
                for correlation_ids in self._pending.values()
                for correlation_id in correlation_ids
            )
            self._pending.clear()
            for correlation_id in pending:
                self._pending_created.pop(correlation_id, None)
                self._sdk_only[correlation_id] = time.monotonic()
            return pending

    def _prune_locked(self) -> None:
        cutoff = time.monotonic() - self._TTL_SECONDS
        self._records = [record for record in self._records if record.created_at >= cutoff]
        self._records_by_correlation = {
            correlation_id: record
            for correlation_id, record in self._records_by_correlation.items()
            if record.created_at >= cutoff
        }
        self._sdk_only = {
            correlation_id: created_at
            for correlation_id, created_at in self._sdk_only.items()
            if created_at >= cutoff
        }
        for key, pending in list(self._pending.items()):
            fresh = [
                correlation_id
                for correlation_id in pending
                if self._pending_created.get(correlation_id, 0.0) >= cutoff
            ]
            if fresh:
                self._pending[key] = fresh[-self._MAX_RECORDS :]
            else:
                self._pending.pop(key, None)
        self._pending_created = {
            correlation_id: created_at
            for correlation_id, created_at in self._pending_created.items()
            if created_at >= cutoff
        }

    @staticmethod
    def _key(agent_name: str | None, tool_name: str, args: Any) -> tuple[str, str, str]:
        try:
            encoded = json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
        except (TypeError, ValueError):
            encoded = repr(args)
        return (
            canonical_trace_actor(agent_name),
            str(tool_name or "unknown_tool"),
            hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        )


class TraceCollector:
    """Produce strictly ordered semantic spans and immediately flush each one.

    ``snapshot`` returns one current state per span, while the callback receives
    the full event stream.  This lets a live client update a span in place after
    its start event without confusing an SDK observation with a second tool
    invocation.
    """

    def __init__(self, trace_id: str, emit: TraceEmit) -> None:
        self.trace_id = trace_id
        self._emit = emit
        self._lock = RLock()
        self._seq = 0
        self._events: list[dict[str, Any]] = []
        self._span_state: dict[str, dict[str, Any]] = {}
        self._span_order: list[str] = []
        self._meta: dict[str, dict[str, Any]] = {}
        self._tool_open: dict[str, list[str]] = defaultdict(list)
        self._lifecycle: dict[str, list[str]] = defaultdict(list)

    def start_span(
        self,
        *,
        phase: TracePhase,
        actor_type: TraceActor,
        actor_name: str,
        parent_span_id: str | None = None,
        title: str | None = None,
        summary: str = "Đang chạy",
        debug: dict[str, Any] | None = None,
    ) -> str:
        """Start an observable operation and return its stable span ID."""
        span_id = f"sp-{uuid.uuid4().hex[:12]}"
        with self._lock:
            self._meta[span_id] = {
                "closed": False,
                "phase": phase,
                "actor_type": actor_type,
                "actor_name": actor_name,
                "parent_span_id": parent_span_id,
                "sources": set(),
            }
            self._emit_span(
                span_id=span_id,
                parent_span_id=parent_span_id,
                phase=phase,
                kind="started",
                actor_type=actor_type,
                actor_name=actor_name,
                display={
                    "title": title or actor_name,
                    "summary": summary,
                    "status": "running",
                },
                metrics={},
                debug=debug or {},
            )
        return span_id

    def finish_span(
        self,
        span_id: str,
        *,
        title: str,
        summary: str,
        latency_ms: float | int | None = None,
        token_usage: dict[str, Any] | None = None,
        debug: dict[str, Any] | None = None,
    ) -> None:
        self._close_span(
            span_id,
            kind="finished",
            title=title,
            summary=summary,
            status="ok",
            latency_ms=latency_ms,
            token_usage=token_usage,
            debug=debug or {},
        )

    def fail_span(
        self,
        span_id: str,
        *,
        code: str,
        summary: str,
        debug: dict[str, Any] | None = None,
    ) -> None:
        self._close_span(
            span_id,
            kind="failed",
            title="Thực thi lỗi",
            summary=summary,
            status=code or "error",
            latency_ms=None,
            token_usage=None,
            debug=debug or {},
        )

    def record(
        self,
        *,
        phase: TracePhase,
        actor_type: TraceActor,
        actor_name: str,
        title: str,
        summary: str,
        status: str = "ok",
        parent_span_id: str | None = None,
        metrics: dict[str, Any] | None = None,
        debug: dict[str, Any] | None = None,
        kind: TraceKind = "finished",
    ) -> str:
        """Emit a one-shot semantic observation with a new span ID."""
        span_id = f"sp-{uuid.uuid4().hex[:12]}"
        with self._lock:
            self._meta[span_id] = {
                "closed": kind != "started",
                "phase": phase,
                "actor_type": actor_type,
                "actor_name": actor_name,
                "parent_span_id": parent_span_id,
                "sources": set(),
            }
            self._emit_span(
                span_id=span_id,
                parent_span_id=parent_span_id,
                phase=phase,
                kind=kind,
                actor_type=actor_type,
                actor_name=actor_name,
                display={"title": title, "summary": summary, "status": status},
                metrics=metrics or {},
                debug=debug or {},
            )
        return span_id

    def snapshot(self) -> list[dict[str, Any]]:
        """Return redacted current state for each span in creation order."""
        with self._lock:
            return [copy.deepcopy(self._span_state[span_id]) for span_id in self._span_order]

    # CrewAI lifecycle observations.  These are intentionally compact: their
    # raw event properties are forwarded only when the SDK actually supplied
    # them, and unavailable fields explicitly say so.
    def observe_crewai_crew_started(self) -> str:
        span_id = self.start_span(
            phase="coordinator",
            actor_type="coordinator",
            actor_name="coordinator",
            title="Điều phối phiên trả lời",
        )
        self._lifecycle["crew"].append(span_id)
        return span_id

    def observe_crewai_crew_finished(
        self, *, token_usage: dict[str, Any] | None = None
    ) -> None:
        span_id = self._pop_lifecycle("crew")
        if span_id:
            self.finish_span(
                span_id,
                title="Hoàn tất điều phối",
                summary="CrewAI đã hoàn tất phản hồi.",
                token_usage=token_usage,
            )

    def observe_crewai_crew_failed(self, error: Any) -> None:
        span_id = self._pop_lifecycle("crew")
        if span_id:
            self.fail_span(
                span_id,
                code=type(error).__name__,
                summary="CrewAI không thể hoàn tất phiên trả lời.",
                debug={"error": str(error)},
            )

    def observe_crewai_agent_started(
        self,
        agent_name: str,
        *,
        task: Any = "not_available",
        goal_prompt: Any = "not_available",
        task_prompt: Any = "not_available",
    ) -> str:
        parent = self._latest_lifecycle("crew")
        span_id = self.start_span(
            phase="agent",
            actor_type="agent",
            actor_name=agent_name or "unknown_agent",
            parent_span_id=parent,
            title=f"Agent: {agent_name or 'unknown_agent'}",
            debug={
                "task": task,
                "goal_prompt": goal_prompt,
                "task_prompt": task_prompt,
            },
        )
        self._lifecycle[f"agent:{agent_name}"].append(span_id)
        return span_id

    def observe_crewai_agent_finished(
        self, agent_name: str, *, output: Any = "not_available"
    ) -> None:
        span_id = self._pop_lifecycle(f"agent:{agent_name}")
        if span_id:
            self.finish_span(
                span_id,
                title=f"Agent: {agent_name}",
                summary="Agent delegated tasks",
                debug={"output": self._available(output)},
            )

    def observe_crewai_agent_failed(self, agent_name: str, error: Any) -> None:
        span_id = self._pop_lifecycle(f"agent:{agent_name}")
        if span_id:
            self.fail_span(
                span_id,
                code=type(error).__name__,
                summary=f"Agent {agent_name} gặp lỗi.",
                debug={"error": str(error)},
            )

    def observe_crewai_task_started(self, task_name: Any = "not_available") -> str:
        normalized = str(task_name) if task_name not in (None, "") else "not_available"
        parent = self._latest_any_agent() or self._latest_lifecycle("crew")
        span_id = self.start_span(
            phase="coordinator",
            actor_type="coordinator",
            actor_name="coordinator",
            parent_span_id=parent,
            title="Bắt đầu task",
            summary=normalized,
            debug={"task": normalized},
        )
        self._lifecycle[f"task:{normalized}"].append(span_id)
        return span_id

    def observe_crewai_task_finished(
        self, task_name: Any = "not_available", *, output: Any = "not_available"
    ) -> None:
        normalized = str(task_name) if task_name not in (None, "") else "not_available"
        span_id = self._pop_lifecycle(f"task:{normalized}")
        if span_id:
            self.finish_span(
                span_id,
                title="Hoàn tất task",
                summary=normalized,
                debug={"output": self._available(output)},
            )

    def observe_crewai_task_failed(self, task_name: Any, error: Any) -> None:
        normalized = str(task_name) if task_name not in (None, "") else "not_available"
        span_id = self._pop_lifecycle(f"task:{normalized}")
        if span_id:
            self.fail_span(
                span_id,
                code=type(error).__name__,
                summary=f"Task {normalized} gặp lỗi.",
                debug={"error": str(error)},
            )

    def observe_crewai_llm_started(
        self, call_id: str, agent_name: str | None, model: Any
    ) -> str:
        parent = self._latest_lifecycle(f"agent:{agent_name}") or self._latest_lifecycle("crew")
        normalized_call_id = str(call_id or uuid.uuid4().hex)
        span_id = self.start_span(
            phase="agent",
            actor_type="agent",
            actor_name=agent_name or "unknown_agent",
            parent_span_id=parent,
            title="Gọi LLM",
            debug={"call_id": normalized_call_id, "model": self._available(model)},
        )
        self._lifecycle[f"llm:{normalized_call_id}"].append(span_id)
        return span_id

    def observe_crewai_llm_finished(
        self,
        call_id: str,
        *,
        duration_ms: float | int | None,
        token_usage: dict[str, Any] | None,
        finish_reason: Any = "not_available",
    ) -> None:
        span_id = self._pop_lifecycle(f"llm:{call_id}")
        if span_id:
            self.finish_span(
                span_id,
                title="LLM response",
                summary="LLM call",
                latency_ms=duration_ms,
                token_usage=token_usage,
                debug={"finish_reason": self._available(finish_reason)},
            )

    def observe_crewai_llm_failed(self, call_id: str, error: Any) -> None:
        span_id = self._pop_lifecycle(f"llm:{call_id}")
        if span_id:
            self.fail_span(
                span_id,
                code=type(error).__name__,
                summary="LLM error",
                debug={"error": str(error)},
            )

    # Tool lifecycle observations.  SDK and gateway events arrive from two
    # layers for the same invocation.  We correlate only an *open* counterpart
    # of the other source, FIFO per tool and parent.  Role names are deliberately
    # not a key because SDK roles and gateway capability names differ.
    def observe_crewai_tool_started(
        self,
        agent_name: str | None,
        tool_name: str,
        args: Any,
        *,
        parent_span_id: str | None = None,
        correlation_id: str | None = None,
    ) -> str:
        return self._start_or_match_tool(
            source="crewai",
            actor_name=agent_name or "unknown_agent",
            tool_name=tool_name,
            args=args,
            parent_span_id=parent_span_id,
            correlation_id=correlation_id,
        )

    def observe_gateway_tool_started(
        self,
        agent_name: str | None,
        tool_name: str,
        args: Any,
        *,
        parent_span_id: str | None = None,
        correlation_id: str | None = None,
    ) -> str:
        return self._start_or_match_tool(
            source="gateway",
            actor_name=agent_name or "gateway",
            tool_name=tool_name,
            args=args,
            parent_span_id=parent_span_id,
            correlation_id=correlation_id,
        )

    def observe_gateway_tool_finished(
        self,
        agent_name: str | None,
        tool_name: str,
        *,
        result: Any,
        latency_ms: float | int | None,
        status: str = "ok",
        span_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        span_id = self._resolve_open_tool(
            span_id,
            tool_name=tool_name,
            actor_name=agent_name,
            preferred_source="gateway",
            correlation_id=correlation_id,
        )
        if not span_id:
            return
        self.finish_span(
            span_id,
            title=f"Tool call: {tool_name}",
            summary=self._tool_summary(tool_name, result, status),
            latency_ms=latency_ms,
            debug={"result": result, "gateway_agent_name": agent_name or "gateway"},
        )

    def observe_gateway_tool_failed(
        self,
        agent_name: str | None,
        tool_name: str,
        *,
        error: Any,
        latency_ms: float | int | None,
        span_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        span_id = self._resolve_open_tool(
            span_id,
            tool_name=tool_name,
            actor_name=agent_name,
            preferred_source="gateway",
            correlation_id=correlation_id,
        )
        if not span_id:
            return
        self.fail_span(
            span_id,
            code=type(error).__name__,
            summary=f"Tool {tool_name} gặp lỗi.",
            debug={
                "error": str(error),
                "latency_ms": latency_ms,
                "gateway_agent_name": agent_name or "gateway",
            },
        )

    def observe_crewai_tool_finished(
        self,
        agent_name: str | None,
        tool_name: str,
        *,
        status: str = "ok",
        correlation_id: str | None = None,
        sdk_only: bool = False,
    ) -> None:
        span_id = self._resolve_open_tool(
            None,
            tool_name=tool_name,
            actor_name=agent_name,
            preferred_source="crewai",
            correlation_id=correlation_id,
        )
        if not span_id:
            return
        with self._lock:
            sources = self._meta[span_id]["sources"]
        if "gateway" in sources:
            # Gateway owns the normalized result and closes this invocation.
            return
        if sdk_only:
            self._finish_sdk_only(
                span_id,
                reason="sdk_completed_without_exact_gateway_link",
                summary="SDK đã hoàn tất tool nhưng không có gateway execution khớp.",
                debug={"sdk_status": status, "sdk_outcome": "finished"},
            )
            return
        self.finish_span(
            span_id,
            title=f"Tool call: {tool_name}",
            summary="Kết quả tool không được SDK cung cấp.",
            debug={
                "result": "not_available",
                "agent_name": agent_name or "unknown_agent",
                "status": status,
            },
        )

    def observe_crewai_tool_failed(
        self,
        agent_name: str | None,
        tool_name: str,
        error: Any,
        *,
        correlation_id: str | None = None,
        sdk_only: bool = False,
    ) -> None:
        span_id = self._resolve_open_tool(
            None,
            tool_name=tool_name,
            actor_name=agent_name,
            preferred_source="crewai",
            correlation_id=correlation_id,
        )
        if not span_id:
            return
        with self._lock:
            sources = self._meta[span_id]["sources"]
        if "gateway" in sources:
            return
        if sdk_only:
            self._finish_sdk_only(
                span_id,
                reason="sdk_error_without_exact_gateway_link",
                summary="SDK báo lỗi tool nhưng không có gateway execution khớp.",
                debug={
                    "sdk_outcome": "error",
                    "sdk_error_code": type(error).__name__,
                    "sdk_error": str(error),
                },
            )
            return
        self.fail_span(
            span_id,
            code=type(error).__name__,
            summary=f"Tool {tool_name} gặp lỗi.",
            debug={"error": str(error), "agent_name": agent_name or "unknown_agent"},
        )

    def observe_crewai_tool_unlinked(self, correlation_id: str, *, reason: str) -> None:
        """Close an SDK-only observation when exact gateway linkage is impossible."""
        with self._lock:
            candidates = [
                span_id
                for span_id, meta in self._meta.items()
                if not meta["closed"] and meta.get("correlation_id") == correlation_id
            ]
        for span_id in candidates:
            self._finish_sdk_only(
                span_id,
                reason=reason,
                summary="Không thể liên kết chính xác với gateway execution.",
            )

    def observe_sdk_gateway_link(
        self,
        span_id: str | None,
        *,
        correlation_id: str | None,
        agent_name: str | None,
    ) -> None:
        """Attach a late native SDK event to an existing gateway span in place."""
        if not span_id:
            return
        with self._lock:
            if span_id not in self._span_state:
                return
            self._merge_span_debug(
                span_id,
                {
                    "sdk_correlation_id": correlation_id or "not_available",
                    "sdk_agent_name": agent_name or "unknown_agent",
                    "link_status": "gateway_authoritative",
                },
            )

    def record_sdk_only_tool(
        self,
        agent_name: str | None,
        tool_name: str,
        args: Any,
        *,
        correlation_id: str | None,
        reason: str,
    ) -> str:
        """Record a terminal SDK observation that cannot be linked exactly."""
        return self.record(
            phase="tool",
            actor_type="tool",
            actor_name=str(tool_name or "unknown_tool"),
            title="SDK quan sát tool",
            summary="Không có liên kết chính xác với gateway execution.",
            status="sdk_only",
            parent_span_id=self._active_agent_parent(agent_name or "unknown_agent"),
            debug={
                "args": args,
                "sdk_agent_name": agent_name or "unknown_agent",
                "sdk_correlation_id": correlation_id or "not_available",
                "link_status": "sdk_only",
                "reason": reason,
            },
        )

    def finalize_unlinked_sdk_tools(self, *, reason: str) -> None:
        """Terminally close SDK-only starts when the native capture ends."""
        with self._lock:
            span_ids = [
                span_id
                for span_id, meta in self._meta.items()
                if not meta["closed"]
                and meta["phase"] == "tool"
                and meta["sources"] == {"crewai"}
            ]
        for span_id in span_ids:
            self._finish_sdk_only(
                span_id,
                reason=reason,
                summary="Không quan sát được gateway execution trước khi phiên kết thúc.",
            )

    def _finish_sdk_only(
        self,
        span_id: str,
        *,
        reason: str,
        summary: str,
        debug: dict[str, Any] | None = None,
    ) -> None:
        self._close_span(
            span_id,
            kind="finished",
            title="SDK đã yêu cầu tool",
            summary=summary,
            status="sdk_only",
            latency_ms=None,
            token_usage=None,
            debug={"link_status": "sdk_only", "reason": reason, **(debug or {})},
        )

    def _start_or_match_tool(
        self,
        *,
        source: Literal["crewai", "gateway"],
        actor_name: str,
        tool_name: str,
        args: Any,
        parent_span_id: str | None,
        correlation_id: str | None,
    ) -> str:
        normalized_tool = str(tool_name or "unknown_tool")
        with self._lock:
            resolved_parent = parent_span_id or self._active_agent_parent(actor_name)
            span_id = self._find_matching_counterpart(
                tool_name=normalized_tool,
                actor_name=actor_name,
                parent_span_id=resolved_parent,
                source=source,
                correlation_id=correlation_id,
            )
            if span_id:
                meta = self._meta[span_id]
                meta["sources"].add(source)
                # The gateway's post-policy args are the authoritative version.
                if source == "gateway":
                    self._merge_span_debug(
                        span_id,
                        {"args": args, "gateway_agent_name": actor_name},
                    )
                return span_id

            span_id = self.start_span(
                phase="tool",
                actor_type="tool",
                actor_name=normalized_tool,
                parent_span_id=resolved_parent,
                title=f"Gọi tool: {normalized_tool}",
                debug={"args": args, f"{source}_agent_name": actor_name},
            )
            self._meta[span_id]["sources"].add(source)
            self._meta[span_id]["correlation_id"] = correlation_id
            self._meta[span_id]["actor_key"] = self._actor_key(actor_name)
            self._tool_open[normalized_tool].append(span_id)
            return span_id

    def _find_matching_counterpart(
        self,
        *,
        tool_name: str,
        actor_name: str,
        parent_span_id: str | None,
        source: Literal["crewai", "gateway"],
        correlation_id: str | None,
    ) -> str | None:
        counterpart = "gateway" if source == "crewai" else "crewai"
        candidates = self._matching_open_tools(
            tool_name=tool_name,
            actor_name=actor_name,
            parent_span_id=parent_span_id,
            required_source=counterpart,
            missing_source=source,
            correlation_id=correlation_id,
        )
        # Without an SDK-provided invocation ID, only merge a unique active
        # candidate. Ambiguity produces a second span rather than a false merge.
        return candidates[0] if len(candidates) == 1 else None

    def _resolve_open_tool(
        self,
        span_id: str | None,
        *,
        tool_name: str,
        actor_name: str | None,
        preferred_source: str,
        correlation_id: str | None,
    ) -> str | None:
        with self._lock:
            if span_id and self._is_open_tool(span_id, tool_name, preferred_source):
                return span_id
        candidates = self._matching_open_tools(
            tool_name=tool_name,
            actor_name=actor_name or "unknown_agent",
            parent_span_id=self._active_agent_parent(actor_name or "unknown_agent"),
            required_source=preferred_source,
            correlation_id=correlation_id,
        )
        return candidates[0] if len(candidates) == 1 else None

    def _matching_open_tools(
        self,
        *,
        tool_name: str,
        actor_name: str,
        parent_span_id: str | None,
        required_source: str | None = None,
        missing_source: str | None = None,
        correlation_id: str | None = None,
    ) -> list[str]:
        matches: list[str] = []
        actor_key = self._actor_key(actor_name)
        with self._lock:
            candidates = self._tool_open.get(tool_name, [])
            for span_id in candidates:
                meta = self._meta.get(span_id)
                if not meta or meta["closed"]:
                    continue
                if parent_span_id != meta["parent_span_id"]:
                    continue
                if meta.get("actor_key") != actor_key:
                    continue
                if required_source and required_source not in meta["sources"]:
                    continue
                if missing_source and missing_source in meta["sources"]:
                    continue
                if correlation_id and meta.get("correlation_id") != correlation_id:
                    continue
                matches.append(span_id)
        return matches

    def _is_open_tool(self, span_id: str, tool_name: str, source: str) -> bool:
        meta = self._meta.get(span_id)
        return bool(
            meta
            and not meta["closed"]
            and meta["actor_name"] == tool_name
            and source in meta["sources"]
        )

    def _active_agent_parent(self, actor_name: str) -> str | None:
        actor_key = self._actor_key(actor_name)
        with self._lock:
            matches: list[str] = []
            for key, values in self._lifecycle.items():
                if key.startswith("agent:") and values and self._actor_key(key[6:]) == actor_key:
                    matches.append(values[-1])
            return matches[-1] if len(matches) == 1 else None

    @staticmethod
    def _actor_key(actor_name: str) -> str:
        return canonical_trace_actor(actor_name)

    def _close_span(
        self,
        span_id: str,
        *,
        kind: Literal["finished", "failed", "cancelled"],
        title: str,
        summary: str,
        status: str,
        latency_ms: float | int | None,
        token_usage: dict[str, Any] | None,
        debug: dict[str, Any],
    ) -> None:
        with self._lock:
            meta = self._meta.get(span_id)
            if not meta or meta["closed"]:
                return
            meta["closed"] = True
            metrics: dict[str, Any] = {}
            if latency_ms is not None:
                metrics["latency_ms"] = round(float(latency_ms), 3)
            if token_usage is not None:
                metrics["token_usage"] = token_usage
            self._emit_span(
                span_id=span_id,
                parent_span_id=meta["parent_span_id"],
                phase=meta["phase"],
                kind=kind,
                actor_type=meta["actor_type"],
                actor_name=meta["actor_name"],
                display={"title": title, "summary": summary, "status": status},
                metrics=metrics,
                debug=debug,
            )

    def _emit_span(
        self,
        *,
        span_id: str,
        parent_span_id: str | None,
        phase: TracePhase,
        kind: TraceKind,
        actor_type: TraceActor,
        actor_name: str,
        display: dict[str, str],
        metrics: dict[str, Any],
        debug: dict[str, Any],
    ) -> None:
        self._seq += 1
        state = self._span_state.get(span_id, {})
        merged_debug = {**state.get("debug", {}), **self._sanitize_debug(debug)}
        merged_metrics = {**state.get("metrics", {}), **RequestTelemetry.sanitize(metrics)}
        event = TraceSpan.model_validate(
            {
                "trace_id": self.trace_id,
                "seq": self._seq,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "phase": phase,
                "kind": kind,
                "actor_type": actor_type,
                "actor_name": actor_name,
                "display": {
                    key: self._bounded_text(value)
                    for key, value in display.items()
                },
                "metrics": merged_metrics,
                "debug": merged_debug,
            }
        ).model_dump(mode="json")
        if span_id not in self._span_state:
            self._span_order.append(span_id)
        self._span_state[span_id] = event
        self._events.append(event)
        # Call under the run lock so concurrently produced events cannot reach
        # a live client out of sequence.  Persistence is intentionally outside
        # this class and therefore cannot precede this flush.
        try:
            self._emit(copy.deepcopy(event))
        except Exception:
            # Observability must not turn a customer response into a failure.
            return

    def _merge_span_debug(self, span_id: str, debug: dict[str, Any]) -> None:
        state = self._span_state.get(span_id)
        if state is None:
            return
        state["debug"] = {**state.get("debug", {}), **self._sanitize_debug(debug)}

    def _pop_lifecycle(self, key: str) -> str | None:
        with self._lock:
            values = self._lifecycle.get(key)
            return values.pop() if values else None

    def _latest_lifecycle(self, key: str) -> str | None:
        with self._lock:
            values = self._lifecycle.get(key)
            return values[-1] if values else None

    def _latest_any_agent(self) -> str | None:
        with self._lock:
            for key in reversed(list(self._lifecycle)):
                if key.startswith("agent:") and self._lifecycle[key]:
                    return self._lifecycle[key][-1]
        return None

    @classmethod
    def _sanitize_debug(cls, value: dict[str, Any]) -> dict[str, Any]:
        return sanitize_trace_debug(value)

    @staticmethod
    def _available(value: Any) -> Any:
        return "not_available" if value in (None, "") else value

    @staticmethod
    def _bounded_text(value: Any) -> str:
        return str(value or "not_available")[:320]

    @staticmethod
    def _tool_summary(tool_name: str, result: Any, status: str) -> str:
        if isinstance(result, dict):
            count = result.get("count")
            if isinstance(count, int):
                return f"{tool_name}: {count} kết quả ({status})."
            if result.get("status"):
                return f"{tool_name}: {result['status']}."
        return f"{tool_name}: {status}."
