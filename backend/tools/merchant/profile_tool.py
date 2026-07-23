"""Merchant profile tool (F-02 Merchant) — Retrieves 8-dimension profile details and evidence breakdown.

Strictly obeys Security Rule C2: `overall_score` is stripped.
"""
from __future__ import annotations

from typing import Any
from sqlalchemy.orm import Session
from database.connection import SessionLocal
from repositories.merchant_profile_repository import MerchantProfileRepository
from tools.allow_list import agents_allowed_for
from tools.registry import ToolRegistry, ToolSpec


def get_profile_evidence(
    merchant_id: str,
    dimension: str | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    """Retrieve 8-dimension profile details and evidence breakdown for a merchant.

    Args:
        merchant_id: Target merchant ID.
        dimension: Optional specific dimension name (e.g. 'waiting_time', 'food_quality').
        db: Optional database session for test injection.

    Returns:
        Dictionary containing profile dimensions and evidence list (overall_score stripped).
    """
    session = db or SessionLocal()
    try:
        repo = MerchantProfileRepository(session)
        profile = repo.get_profile(merchant_id)
        if not profile:
            return {
                "merchant_id": merchant_id,
                "status": "not_found",
                "dimensions": {},
            }

        if dimension:
            return repo.get_dimension_evidence(merchant_id, dimension)

        return {
            "merchant_id": merchant_id,
            "tier": profile.get("tier", "standard"),
            "dimensions": profile.get("dimensions", {}),
            "attributes": profile.get("attributes", {}),
        }
    finally:
        if db is None:
            session.close()


def register(reg: ToolRegistry) -> None:
    """Auto-discovery entry point for profile tools."""
    reg.register(
        ToolSpec(
            name="get_profile_evidence",
            description="Retrieve a merchant's 8-dimension profile and evidence breakdown.",
            input_schema={"merchant_id": "str", "dimension": "str?"},
            output_schema={"merchant_id": "str", "dimensions": "dict"},
            allowed_agents=agents_allowed_for("get_profile_evidence"),
            cache_policy="profile_snapshot",
            source_kind="real",
        ),
        get_profile_evidence,
    )
