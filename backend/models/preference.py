"""User profile + preference event / delta contracts (design §6.5, §6.6, §11.6).

FROZEN SEAM (owner: Dev A). preference_events never replace user_profiles (§6.2);
the frontend cannot PATCH user_profiles with arbitrary JSON (§11.6).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

PREFERENCE_OPERATIONS: tuple[str, ...] = ("add", "remove", "set")
# Profile Delta scopes — design §7.1 (session applies now; candidate_global shows
# confirmation; confirmed_global persists to Postgres).
PREFERENCE_SCOPES: tuple[str, ...] = ("session", "candidate_global", "confirmed_global")
# Candidate statuses — design §7.1.
PREFERENCE_STATUS: tuple[str, ...] = ("candidate", "confirmed", "rejected", "expired")


class UserProfilePublic(BaseModel):
    """§6.5 user profile contract."""

    user_id: str
    liked_cuisines: list[str] = Field(default_factory=list)
    disliked_cuisines: list[str] = Field(default_factory=list)
    spice_tolerance: str | None = None  # none | mild | medium | hot
    dietary: list[str] = Field(default_factory=list)
    budget_level: str | None = None  # student | standard | premium
    distance_preference_km: float = 5.0
    current_lat: float | None = None
    current_lng: float | None = None
    context_memory: dict[str, Any] = Field(default_factory=dict)
    updated_at: str | None = None


class PreferenceEvent(BaseModel):
    """§6.6 append-only preference audit record."""

    event_id: str
    user_id: str
    session_id: str | None = None
    field: str
    operation: str
    value: Any
    scope: str
    source: str
    confidence: float = 1.0
    status: str = "candidate"
    evidence_refs: list[str] = Field(default_factory=list)
    created_at: str
    expires_at: str | None = None
    resolved_at: str | None = None


class ProfileDeltaSuggestion(BaseModel):
    """A candidate change surfaced in chat (never auto-applied)."""

    delta_id: str
    field: str
    operation: str
    value: Any
    confidence: float
    rationale: str | None = None
