"""Agent Run Service (J-01, J-02, J-03) — Management layer for trace execution persistence.

Manages agent_runs and agent_events records in PostgreSQL.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import AgentRun, AgentEvent
from core.errors import NotFoundError


class AgentRunService:
    """Service layer for recording and retrieving Agent run traces and events."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def start_run(
        self,
        trace_id: str | None = None,
        crew_name: str = "merchant_advisor_crew",
        session_id: str | None = None,
        user_id: str | None = None,
        intent: str | None = None,
    ) -> AgentRun:
        """Start a new agent run trace."""
        tid = trace_id or f"tr-{uuid.uuid4().hex[:12]}"
        run = AgentRun(
            trace_id=tid,
            session_id=session_id,
            user_id=user_id,
            crew_name=crew_name,
            intent=intent,
            status="running",
            started_at=datetime.utcnow(),
        )
        self._db.add(run)
        self._db.commit()
        self._db.refresh(run)
        return run

    def record_event(
        self,
        trace_id: str,
        event_type: str,
        agent_name: str | None = None,
        task_name: str | None = None,
        tool_name: str | None = None,
        input_hash: str | None = None,
        output_summary_json: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        status: str = "ok",
        error_code: str | None = None,
        parent_event_id: str | None = None,
    ) -> AgentEvent:
        """Record a sub-event (tool execution, task step, delegation) for a trace."""
        event_id = f"evt-{uuid.uuid4().hex[:12]}"
        event = AgentEvent(
            event_id=event_id,
            trace_id=trace_id,
            parent_event_id=parent_event_id,
            event_type=event_type,
            agent_name=agent_name,
            task_name=task_name,
            tool_name=tool_name,
            input_hash=input_hash,
            output_summary_json=output_summary_json,
            duration_ms=duration_ms,
            status=status,
            error_code=error_code,
            created_at=datetime.utcnow(),
        )
        self._db.add(event)
        self._db.commit()
        self._db.refresh(event)
        return event

    def finish_run(
        self,
        trace_id: str,
        status: str = "completed",
        error_code: str | None = None,
        token_usage_json: dict[str, Any] | None = None,
    ) -> AgentRun:
        """Mark an agent run as finished."""
        run = self._db.get(AgentRun, trace_id)
        if not run:
            raise NotFoundError(
                f"Không tìm thấy trace '{trace_id}'.",
                details={"trace_id": trace_id},
            )
        run.status = status
        run.finished_at = datetime.utcnow()
        if error_code:
            run.error_code = error_code
        if token_usage_json:
            run.token_usage_json = token_usage_json

        self._db.commit()
        self._db.refresh(run)
        return run

    def get_run_trace(self, trace_id: str) -> dict[str, Any]:
        """Retrieve full trace details and ordered event list for J-03 API."""
        run = self._db.get(AgentRun, trace_id)
        if not run:
            raise NotFoundError(
                f"Không tìm thấy trace '{trace_id}'.",
                details={"trace_id": trace_id},
            )

        stmt = (
            select(AgentEvent)
            .where(AgentEvent.trace_id == trace_id)
            .order_by(AgentEvent.created_at.asc())
        )
        events = list(self._db.execute(stmt).scalars().all())

        return {
            "trace_id": run.trace_id,
            "session_id": run.session_id,
            "user_id": run.user_id,
            "crew_name": run.crew_name,
            "intent": run.intent,
            "status": run.status,
            "started_at": str(run.started_at) if run.started_at else None,
            "finished_at": str(run.finished_at) if run.finished_at else None,
            "error_code": run.error_code,
            "token_usage": run.token_usage_json,
            "events": [
                {
                    "event_id": e.event_id,
                    "event_type": e.event_type,
                    "agent_name": e.agent_name,
                    "task_name": e.task_name,
                    "tool_name": e.tool_name,
                    "input_hash": e.input_hash,
                    "output_summary": e.output_summary_json,
                    "duration_ms": e.duration_ms,
                    "status": e.status,
                    "error_code": e.error_code,
                    "created_at": str(e.created_at) if e.created_at else None,
                }
                for e in events
            ],
        }
