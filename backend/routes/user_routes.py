"""User profile, deltas, sessions (Dev A). FROZEN paths — design §11.6/§11.9."""
from __future__ import annotations

from fastapi import APIRouter

from routes.stub_helpers import not_implemented

router = APIRouter(prefix="/api/v1/users", tags=["user"])


@router.get("/{user_id}/profile")
def get_user_profile(user_id: str) -> object:
    return not_implemented(f"GET /api/v1/users/{user_id}/profile")


@router.post("/{user_id}/profile/deltas/{delta_id}/confirm")
def confirm_delta(user_id: str, delta_id: str) -> object:
    return not_implemented("POST .../profile/deltas/{id}/confirm")


@router.post("/{user_id}/profile/deltas/{delta_id}/reject")
def reject_delta(user_id: str, delta_id: str) -> object:
    return not_implemented("POST .../profile/deltas/{id}/reject")


@router.delete("/{user_id}/preferences/{field}")
def delete_preference(user_id: str, field: str) -> object:
    return not_implemented("DELETE .../preferences/{field}")


@router.get("/{user_id}/sessions")
def list_sessions(user_id: str) -> object:
    return not_implemented(f"GET /api/v1/users/{user_id}/sessions")
