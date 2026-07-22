"""Reference CrewAI event listener + emission helper — FROZEN SEAM (Feature J, H8).

The listener contract is `models.agent.AgentEventRecord`. Both flows emit events via
`build_event_record(...)`; Dev B's real listener persists them to `agent_events`. Shipping
a reference here means each vertical verifies emission (trace_id, input_hash, duration…)
on its OWN branch — the H8 contract test asserts no required field is missing, so a
missing field is caught pre-merge, not at Phase 3 integration.

No hard CrewAI import: the persistence side (Dev B) can subclass CrewAI's BaseEventListener
and delegate to `RecordingListener.handle`.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from core.tracing import new_id
from models.agent import AGENT_EVENT_TYPES, REQUIRED_EMIT_FIELDS, AgentEventRecord


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def input_hash(payload: Any) -> str:
    """Stable hash of tool/task input for the trace (never stores raw secrets)."""
    blob = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def build_event_record(
    *,
    trace_id: str,
    event_type: str,
    agent_name: str | None = None,
    task_name: str | None = None,
    tool_name: str | None = None,
    input_payload: Any = None,
    output_summary: dict[str, Any] | None = None,
    duration_ms: int | None = None,
    status: str = "ok",
    error_code: str | None = None,
    parent_event_id: str | None = None,
) -> AgentEventRecord:
    """Construct a fully-populated event record. Raises if event_type is unknown."""
    if event_type not in AGENT_EVENT_TYPES:
        raise ValueError(f"unknown agent event_type: {event_type}")
    return AgentEventRecord(
        event_id=new_id("evt"),
        trace_id=trace_id,
        parent_event_id=parent_event_id,
        event_type=event_type,
        agent_name=agent_name,
        task_name=task_name,
        tool_name=tool_name,
        input_hash=input_hash(input_payload) if input_payload is not None else None,
        output_summary=output_summary or {},
        duration_ms=duration_ms,
        status=status,
        error_code=error_code,
        created_at=_utc_now_iso(),
    )


def assert_emittable(record: AgentEventRecord) -> None:
    """Guard used by the H8 contract test: every REQUIRED_EMIT_FIELD is present."""
    data = record.model_dump()
    missing = [f for f in REQUIRED_EMIT_FIELDS if not data.get(f)]
    if missing:
        raise ValueError(f"event missing required fields: {missing}")


class RecordingListener:
    """Minimal in-memory reference listener. Dev B swaps the sink for the DB repository."""

    def __init__(self) -> None:
        self.events: list[AgentEventRecord] = []

    def handle(self, record: AgentEventRecord) -> None:
        assert_emittable(record)
        self.events.append(record)
