"""Interaction events (Dev A). FROZEN path — design §11.7."""
from __future__ import annotations

from fastapi import APIRouter

from routes.stub_helpers import not_implemented

router = APIRouter(prefix="/api/v1/users", tags=["events"])


@router.post("/{user_id}/events")
def record_event(user_id: str) -> object:
    return not_implemented(f"POST /api/v1/users/{user_id}/events")
