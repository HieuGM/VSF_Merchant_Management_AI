"""Session + agent-run trace inspection (Dev B, admin-only). FROZEN — design §11.9."""
from __future__ import annotations

from fastapi import APIRouter

from routes.stub_helpers import not_implemented

router = APIRouter(prefix="/api/v1", tags=["trace"])


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> object:
    return not_implemented(f"GET /api/v1/sessions/{session_id}")


@router.get("/agent/runs/{trace_id}")
def get_run(trace_id: str) -> object:
    return not_implemented(f"GET /api/v1/agent/runs/{trace_id}")
