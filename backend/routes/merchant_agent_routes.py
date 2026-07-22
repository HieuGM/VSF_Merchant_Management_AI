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

