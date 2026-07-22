"""Interaction event contract (design §6.2 interaction_events, §11.7).

FROZEN SEAM (owner: Dev A). Interaction events are evidence only and cannot directly
mutate user_profiles (§6.2).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

INTERACTION_EVENT_TYPES: tuple[str, ...] = (
    "MENU_CLICKED",
    "MERCHANT_VIEWED",
    "SEARCH_SUBMITTED",
    "RESULT_SELECTED",
    "PREFERENCE_CONFIRMED",
    "PREFERENCE_REJECTED",
)


class InteractionEventIn(BaseModel):
    """§11.7 request body."""

    session_id: str | None = None
    event_type: str
    merchant_id: str | None = None
    menu_item_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InteractionEvent(InteractionEventIn):
    """Persisted record — adds identity + timestamp."""

    event_id: str
    user_id: str
    created_at: str
