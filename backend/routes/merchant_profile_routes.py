"""Merchant profile + evidence (Dev B). FROZEN paths — design §11.3."""
from __future__ import annotations

from fastapi import APIRouter

from routes.stub_helpers import not_implemented

router = APIRouter(prefix="/api/v1/merchants", tags=["merchant-profile"])


@router.get("/{merchant_id}/profile")
def get_merchant_profile(merchant_id: str) -> object:
    return not_implemented(f"GET /api/v1/merchants/{merchant_id}/profile")


@router.get("/{merchant_id}/evidence/{evidence_type}/{evidence_id}")
def get_evidence(merchant_id: str, evidence_type: str, evidence_id: str) -> object:
    return not_implemented("GET /api/v1/merchants/{id}/evidence/{type}/{id}")
