"""Merchant Profile Repository (C-02) — Single unified data access layer for 8-dimension profiles.

Ensures strict compliance with Security Rule C2:
- `overall_score` MUST be stripped from external surfaces (dict outputs / models).
- Uses `profile_json` as the single authoritative schema version.
"""
from __future__ import annotations

from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import MerchantProfile
from core.errors import NotFoundError


class MerchantProfileRepository:
    """Repository for managing merchant 8-dimension profiles."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_profile(self, merchant_id: str) -> dict[str, Any] | None:
        """Fetch 8-dimension profile for a merchant with overall_score stripped (§6.4 C2)."""
        stmt = select(MerchantProfile).where(MerchantProfile.merchant_id == merchant_id)
        profile_obj = self._db.execute(stmt).scalar_one_or_none()

        if not profile_obj or not profile_obj.profile_json:
            return None

        return self._strip_internal_overall_score(profile_obj.profile_json)

    def get_profile_or_raise(self, merchant_id: str) -> dict[str, Any]:
        """Fetch merchant profile or raise NotFoundError."""
        profile = self.get_profile(merchant_id)
        if not profile:
            raise NotFoundError(
                f"Không tìm thấy hồ sơ merchant '{merchant_id}'.",
                details={"merchant_id": merchant_id},
            )
        return profile

    def save_profile(
        self,
        merchant_id: str,
        profile_data: dict[str, Any],
        source_kind: str = "real",
        schema_version: str = "1.0",
    ) -> MerchantProfile:
        """Save or update merchant profile snapshot (single profile_json schema)."""
        stmt = select(MerchantProfile).where(MerchantProfile.merchant_id == merchant_id)
        existing = self._db.execute(stmt).scalar_one_or_none()

        dimensions = profile_data.get("dimensions", {})

        if existing:
            existing.profile_json = profile_data
            existing.dimensions_json = dimensions
            existing.source_kind = source_kind
            existing.schema_version = schema_version
            profile_record = existing
        else:
            profile_record = MerchantProfile(
                merchant_id=merchant_id,
                dimensions_json=dimensions,
                profile_json=profile_data,
                schema_version=schema_version,
                source_kind=source_kind,
            )
            self._db.add(profile_record)

        self._db.commit()
        self._db.refresh(profile_record)
        return profile_record

    @staticmethod
    def _strip_internal_overall_score(data: dict[str, Any]) -> dict[str, Any]:
        """Deep copy and strip overall_score from top-level and dimensions (§6.4 [C2])."""
        cleaned = dict(data)
        cleaned.pop("overall_score", None)

        if "dimensions" in cleaned and isinstance(cleaned["dimensions"], dict):
            dims = dict(cleaned["dimensions"])
            dims.pop("overall_score", None)
            cleaned["dimensions"] = dims

        return cleaned
