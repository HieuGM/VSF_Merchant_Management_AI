"""Agent run + event persistence (Phase 06) — writes agent_runs / agent_events (§6.2).

Maps the Pydantic listener contracts (`AgentRunRecord`, `AgentEventRecord`) to the ORM
rows. Manages its own SessionLocal per call so callers (flow, listener) never pass a
session. JSONB columns use the `*_json` suffix.

⚠️ Ownership: agent_run persistence is nominally Dev B territory (agent_run_service). The
merged Track A owner implements it here; flag for Phase 3 reconcile if the split returns.
"""
from __future__ import annotations

from datetime import datetime, timezone

from database.connection import SessionLocal
from database.models import AgentEvent, AgentRun
from models.agent import AgentEventRecord, AgentRunRecord


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class AgentRunRepository:
    """Persistence for CrewAI run lifecycle + trace events."""

    def create_run(self, record: AgentRunRecord) -> None:
        """Insert one agent_runs row (status=running at start)."""
        db = SessionLocal()
        try:
            db.merge(
                AgentRun(
                    trace_id=record.trace_id,
                    session_id=record.session_id,
                    user_id=record.user_id,
                    crew_name=record.crew_name,
                    intent=record.intent,
                    status=record.status,
                    started_at=_parse_ts(record.started_at),
                    finished_at=_parse_ts(record.finished_at),
                    error_code=record.error_code,
                    token_usage_json=record.token_usage or {},
                )
            )
            db.commit()
        finally:
            db.close()

    def finish_run(
        self,
        trace_id: str,
        *,
        status: str,
        error_code: str | None = None,
        finished_at: str | None = None,
        token_usage: dict | None = None,
    ) -> None:
        """Update an existing run's terminal status/finished_at."""
        db = SessionLocal()
        try:
            run = db.get(AgentRun, trace_id)
            if run is None:
                return
            run.status = status
            run.error_code = error_code
            run.finished_at = _parse_ts(finished_at) or datetime.now(timezone.utc)
            if token_usage is not None:
                run.token_usage_json = token_usage
            db.commit()
        finally:
            db.close()

    def add_event(self, record: AgentEventRecord) -> None:
        """Append one agent_events row for the trace."""
        db = SessionLocal()
        try:
            db.add(
                AgentEvent(
                    event_id=record.event_id,
                    trace_id=record.trace_id,
                    parent_event_id=record.parent_event_id,
                    event_type=record.event_type,
                    agent_name=record.agent_name,
                    task_name=record.task_name,
                    tool_name=record.tool_name,
                    input_hash=record.input_hash,
                    output_summary_json=record.output_summary or {},
                    duration_ms=record.duration_ms,
                    status=record.status,
                    error_code=record.error_code,
                    created_at=_parse_ts(record.created_at),
                )
            )
            db.commit()
        finally:
            db.close()
