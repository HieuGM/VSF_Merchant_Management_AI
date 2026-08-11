"""User-liked-merchant repository — episodic memory current-state (phase-05).

Holds the durable CURRENT set of a user's liked merchants (the ``user_liked_merchants`` table).
The composite PK makes the toggle idempotent (re-liking is a no-op). The append-only
``interaction_events`` log keeps the like/unlike history — the substrate for future time-decay;
THIS table is the ranking/recall read-path. Caller owns the Session; mutations commit inside each
method (mirrors ``UserProfileRepository``)."""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from database.models import Merchant, UserLikedMerchant


class UserLikedMerchantRepository:
    """Read/toggle the current-state of a user's liked merchants."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def like(self, user_id: str, merchant_id: str) -> None:
        """Idempotent: INSERT (user, merchant); no-op if already liked. Commits.

        The merchants FK raises IntegrityError for an unknown merchant_id — the route maps that
        to 404. on_conflict_do_nothing makes re-liking safe under concurrent calls."""
        stmt = (
            insert(UserLikedMerchant)
            .values(user_id=user_id, merchant_id=merchant_id)
            .on_conflict_do_nothing(index_elements=["user_id", "merchant_id"])
        )
        self._db.execute(stmt)
        self._db.commit()

    def unlike(self, user_id: str, merchant_id: str) -> None:
        """Remove the like if present; no-op if not liked. Commits."""
        self._db.execute(
            delete(UserLikedMerchant).where(
                UserLikedMerchant.user_id == user_id,
                UserLikedMerchant.merchant_id == merchant_id,
            )
        )
        self._db.commit()

    def is_liked(self, user_id: str, merchant_id: str) -> bool:
        return self._db.get(UserLikedMerchant, (user_id, merchant_id)) is not None

    def liked_ids(self, user_id: str) -> set[str]:
        """The set of liked merchant_ids for the user (ranking + FE heart-state)."""
        return set(
            self._db.scalars(
                select(UserLikedMerchant.merchant_id).where(UserLikedMerchant.user_id == user_id)
            )
        )

    def list_details(self, user_id: str) -> list[tuple[str, str | None, str | None]]:
        """(merchant_id, name, cuisine) for the user's likes, newest-first — JOINs merchants.

        Feeds both the UserProfilePublic enrichment (ids + cuisines, so ranking boosts liked
        merchants + same-cuisine ones) and the FE liked-merchants list (ids + names)."""
        rows = self._db.execute(
            select(UserLikedMerchant.merchant_id, Merchant.name, Merchant.cuisine)
            .join(Merchant, Merchant.merchant_id == UserLikedMerchant.merchant_id)
            .where(UserLikedMerchant.user_id == user_id)
            .order_by(UserLikedMerchant.liked_at.desc())
        ).all()
        return [(r[0], r[1], r[2]) for r in rows]
