"""Merchant Advisor chat (Dev B). FROZEN path — design §11.5."""
from __future__ import annotations

from fastapi import APIRouter

from routes.stub_helpers import not_implemented

router = APIRouter(prefix="/api/v1/agent/merchant", tags=["merchant-agent"])


@router.post("/chat")
def merchant_chat() -> object:
    return not_implemented("POST /api/v1/agent/merchant/chat")
