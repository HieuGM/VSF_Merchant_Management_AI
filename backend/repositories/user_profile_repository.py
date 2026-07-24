"""User profile repository (Phase 02) — read access for the Customer Crew.

Maps the `user_profiles` ORM row to the public `UserProfilePublic` contract (§6.5).
Repository receives a Session; it never opens/closes one (the tool layer owns the
SessionLocal lifecycle)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from database.models import UserProfile
from models.preference import UserProfilePublic


class UserProfileRepository:
    """Read access to confirmed user preference profiles."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, user_id: str) -> UserProfilePublic | None:
        row = self._db.get(UserProfile, user_id)
        if row is None:
            return None
        return self._to_public(row)

    @staticmethod
    def _to_public(row: UserProfile) -> UserProfilePublic:
        return UserProfilePublic(
            user_id=row.user_id,
            liked_cuisines=row.liked_cuisines or [],
            disliked_cuisines=row.disliked_cuisines or [],
            spice_tolerance=row.spice_tolerance,
            dietary=row.dietary or [],
            budget_level=row.budget_level,
            distance_preference_km=(
                row.distance_preference_km if row.distance_preference_km is not None else 5.0
            ),
            current_lat=row.current_lat,
            current_lng=row.current_lng,
            context_memory=row.context_memory or {},
            updated_at=row.updated_at.isoformat() if row.updated_at else None,
        )
