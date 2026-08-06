"""Merchant profile + evidence (Dev B). FROZEN paths — design §11.3.

Phase 0b / Task 5: Implement real GET /api/v1/merchants/{merchant_id}/profile.
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database.connection import get_db_session
from repositories.merchant_profile_repository import MerchantProfileRepository
from repositories.merchant_repository import MerchantRepository
from routes.stub_helpers import not_implemented

router = APIRouter(prefix="/api/v1/merchants", tags=["merchant-profile"])


@router.get("/demo-targets")
def list_demo_target_merchants(
    db: Session = Depends(get_db_session),
) -> dict[str, list[dict[str, str]]]:
    """List active merchants explicitly enabled for the merchant demo UI."""
    merchants = MerchantRepository(db).list_demo_targets()
    return {
        "merchants": [
            {
                "merchant_id": merchant.merchant_id,
                "name": merchant.name,
                "city": merchant.city,
                "cuisine": merchant.cuisine,
            }
            for merchant in merchants
        ]
    }


@router.get("/{merchant_id}/profile")
def get_merchant_profile(
    merchant_id: str, db: Session = Depends(get_db_session)
) -> dict[str, Any]:
    """Retrieve 8-dimension performance profile for a merchant (overall_score stripped per C2)."""
    return MerchantProfileRepository(db).get_profile_or_raise(merchant_id)


@router.get("/{merchant_id}/evidence/{evidence_type}/{evidence_id}")
def get_evidence(merchant_id: str, evidence_type: str, evidence_id: str) -> object:
    return not_implemented("GET /api/v1/merchants/{id}/evidence/{type}/{id}")
