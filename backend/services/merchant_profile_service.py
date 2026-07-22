"""Merchant Profile Service (C-05) — Business logic layer for merchant 8-dimension profiles.
"""
from __future__ import annotations

from typing import Any
from sqlalchemy.orm import Session
from repositories.merchant_profile_repository import MerchantProfileRepository
from core.errors import NotFoundError


class MerchantProfileService:
    """Service layer for merchant profile retrieval and formatting."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._repo = MerchantProfileRepository(db)

    def get_profile_view(self, merchant_id: str) -> dict[str, Any]:
        """Fetch merchant profile formatted for API/Agent consumption with C2 security rule enforced."""
        profile = self._repo.get_profile(merchant_id)
        if not profile:
            raise NotFoundError(
                f"Không tìm thấy hồ sơ merchant '{merchant_id}'.",
                details={"merchant_id": merchant_id},
            )
        return profile
