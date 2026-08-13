"""Session + agent-run trace inspection (Dev B). FROZEN paths — design §11.9.

GET /sessions/{session_id} is implemented as the conversation-history DETAIL endpoint
(reopen a past chat): returns the session meta + all its messages so the FE can re-render.
Read-only on an unguessable session_id, kept unguarded like GET /profile.
GET /agent/runs/{trace_id} remains a Phase-0 stub."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.dependencies import get_db_session
from repositories.chat_message_repository import ChatMessageRepository
from repositories.session_repository import SessionRepository
from routes.stub_helpers import not_implemented

router = APIRouter(prefix="/api/v1", tags=["trace"])


@router.get("/sessions/{session_id}")
def get_session(session_id: str, db: Session = Depends(get_db_session)) -> dict:
    """Reopen a past conversation: the session meta + all messages (chronological, with the
    stored agent result cards). 404 when the session does not exist. Read-only.

    TODO(AUTH): like GET /profile and /liked-merchants this read is unguarded, trusting the
    unguessable session_id (dev-only trust model). When real auth replaces require_dev_only,
    add a principal + ownership check (session.user_id == principal) — messages carry
    free-text the user typed (location/preferences), so this is obscurity, not auth."""

    meta = SessionRepository(db).get_session_meta(session_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="session not found")
    messages = ChatMessageRepository(db).list_turns(session_id)
    return {**meta, "messages": messages}


@router.get("/agent/runs/{trace_id}")
def get_run(trace_id: str) -> object:
    return not_implemented(f"GET /api/v1/agent/runs/{trace_id}")
