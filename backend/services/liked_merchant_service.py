"""Liked-merchant service — episodic-memory toggle + audit (phase-05).

Owns the SessionLocal lifecycle around ``UserLikedMerchantRepository`` and appends an
``interaction_events`` audit row on each like/unlike (the append-only history that is the
substrate for future time-decay). The audit is best-effort (F3) — it never breaks the toggle.
An unknown ``merchant_id`` surfaces as an ``IntegrityError`` from the merchants FK; the route
maps that to 404."""
from __future__ import annotations

from database.connection import SessionLocal
from database.models import InteractionEvent
from core.logging import get_logger
from core.tracing import new_id
from repositories.user_liked_merchant_repository import UserLikedMerchantRepository
from repositories.user_profile_repository import UserProfileRepository

_LOG = get_logger(__name__)
# Cap the FE list payload — a user won't like thousands; bounds the response + the in-memory set.
_MAX_LIST = 50


class LikedMerchantService:
    """Toggle + list a user's liked merchants (durable current-state + audit trail)."""

    def list_liked(self, user_id: str) -> list[dict]:
        db = SessionLocal()
        try:
            rows = UserLikedMerchantRepository(db).list_details(user_id)[:_MAX_LIST]
            return [{"merchant_id": mid, "name": name, "cuisine": cui} for mid, name, cui in rows]
        finally:
            db.close()

    def like(self, user_id: str, merchant_id: str, session_id: str | None = None) -> None:
        db = SessionLocal()
        try:
            # Ensure the user_profiles parent row exists (FK target) — a brand-new user who never
            # saved a taste preference has no row, which would otherwise violate the user_id FK.
            # Explicit flush: the Core insert in repo.like() needs the parent row materialized.
            UserProfileRepository._get_or_create_row(db, user_id)
            db.flush()
            UserLikedMerchantRepository(db).like(user_id, merchant_id)  # commits (row + like)
            self._audit(db, user_id, "merchant_liked", merchant_id, session_id)
        finally:
            db.close()

    def unlike(self, user_id: str, merchant_id: str, session_id: str | None = None) -> None:
        db = SessionLocal()
        try:
            UserLikedMerchantRepository(db).unlike(user_id, merchant_id)
            self._audit(db, user_id, "merchant_unliked", merchant_id, session_id)
        finally:
            db.close()

    @staticmethod
    def _audit(
        db, user_id: str, event_type: str, merchant_id: str, session_id: str | None
    ) -> None:
        """Append the like/unlike to interaction_events (best-effort — never breaks the toggle)."""
        try:
            db.add(
                InteractionEvent(
                    event_id=new_id("evt"),
                    user_id=user_id,
                    session_id=session_id,
                    event_type=event_type,
                    merchant_id=merchant_id,
                )
            )
            db.commit()
        except Exception as exc:  # noqa: BLE001 — audit must never break the memory flow
            _LOG.warning("liked-merchant audit failed (%s %s): %s", event_type, merchant_id, exc)


liked_merchant_service = LikedMerchantService()
