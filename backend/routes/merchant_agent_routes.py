"""Merchant Advisor chat (Dev B). FROZEN path — design §11.5.
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.connection import get_db_session
from flows.merchant_flow import merchant_flow


class MerchantChatRequest(BaseModel):
    user_id: str | None = Field(None, description="User ID")
    session_id: str | None = Field(None, description="Session ID for chat conversation history")
    merchant_id: str = Field(..., description="Target merchant ID")
    message: str = Field(..., description="User query or message")
    intent: str | None = Field(None, description="Optional intent override")
    competitor_radius_km: float = Field(5.0, description="Competitor search radius in km")


router = APIRouter(prefix="/api/v1/agent/merchant", tags=["merchant-agent"])


@router.post("/chat")
def merchant_chat(
    req: MerchantChatRequest, db: Session = Depends(get_db_session)
) -> dict[str, Any]:
    """Process a chat request for the Merchant Advisor Agent flow (Design §11.5)."""
    return merchant_flow.chat(
        merchant_id=req.merchant_id,
        message=req.message,
        session_id=req.session_id,
        user_id=req.user_id,
        db=db,
    )


@router.post("/chat/stream")
def merchant_chat_stream(
    req: MerchantChatRequest, db: Session = Depends(get_db_session)
):
    """Process a chat request and return SSE stream."""
    return StreamingResponse(
        merchant_flow.chat_stream(
            merchant_id=req.merchant_id,
            message=req.message,
            session_id=req.session_id,
            user_id=req.user_id,
            db=db,
        ),
        media_type="text/event-stream",
    )


@router.get("/chat/history")
def merchant_chat_history(
    session_id: str, db: Session = Depends(get_db_session)
) -> dict[str, Any]:
    """Retrieve chat message history for a given session."""
    from services.chat_session_service import ChatSessionService
    session_svc = ChatSessionService(db)
    history = session_svc.get_recent_history(session_id, limit=50)
    return {"session_id": session_id, "messages": history}


class CreateSessionRequest(BaseModel):
    merchant_id: str = Field(..., description="Target merchant ID")
    title: str | None = Field(None, description="Optional title")


@router.get("/sessions")
def list_merchant_sessions(
    merchant_id: str = "94", db: Session = Depends(get_db_session)
) -> dict[str, Any]:
    """Retrieve all chat sessions for a given merchant."""
    from services.chat_session_service import ChatSessionService
    session_svc = ChatSessionService(db)
    sessions = session_svc.list_merchant_sessions(merchant_id=merchant_id)
    return {"merchant_id": merchant_id, "sessions": sessions}


@router.post("/sessions")
def create_merchant_session(
    req: CreateSessionRequest, db: Session = Depends(get_db_session)
) -> dict[str, Any]:
    """Create a new chat session for a merchant."""
    from services.chat_session_service import ChatSessionService
    session_svc = ChatSessionService(db)
    session_obj = session_svc.get_or_create_session(
        title=req.title,
        context_snapshot={"merchant_id": req.merchant_id},
    )
    return {
        "session_id": session_obj.session_id,
        "title": session_obj.title,
        "merchant_id": req.merchant_id,
        "created_at": session_obj.created_at.isoformat() if session_obj.created_at else None,
    }


@router.delete("/sessions/{session_id}")
def delete_merchant_session(
    session_id: str, db: Session = Depends(get_db_session)
) -> dict[str, Any]:
    """Delete a chat session and its messages."""
    from services.chat_session_service import ChatSessionService
    session_svc = ChatSessionService(db)
    success = session_svc.delete_session(session_id)
    return {"status": "ok" if success else "not_found", "session_id": session_id}

