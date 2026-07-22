"""Customer Discovery chat (Dev A). FROZEN path — design §11.4."""
from __future__ import annotations

from fastapi import APIRouter

from routes.stub_helpers import not_implemented

router = APIRouter(prefix="/api/v1/agent/customer", tags=["customer-agent"])


@router.post("/chat")
def customer_chat() -> object:
    return not_implemented("POST /api/v1/agent/customer/chat")
