"""Session + agent-run trace inspection (Dev B, admin-only). FROZEN — design §11.9.

Phase 0b / Task 4: Replace 501 stub for GET /api/v1/agent/runs/{trace_id} with real implementation.
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database.connection import get_db_session
from services.agent_run_service import AgentRunService
from routes.stub_helpers import not_implemented

router = APIRouter(prefix="/api/v1", tags=["trace"])


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> object:
    return not_implemented(f"GET /api/v1/sessions/{session_id}")


@router.get("/agent/runs/{trace_id}")
def get_run(
    trace_id: str, db: Session = Depends(get_db_session)
) -> dict[str, Any]:
    """Retrieve execution trace and ordered event history for a given trace_id (UC-J-03)."""
    svc = AgentRunService(db)
    return svc.get_run_trace(trace_id)
