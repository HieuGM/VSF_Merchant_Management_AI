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


from sqlalchemy import select
from database.models import Review, MenuItem, PolicyDocument, MerchantProfile, Merchant


@router.get("/{merchant_id}/profile")
def get_merchant_profile(
    merchant_id: str, db: Session = Depends(get_db_session)
) -> dict[str, Any]:
    """Retrieve 8-dimension performance profile for a merchant."""
    return MerchantProfileRepository(db).get_profile_or_raise(merchant_id)


@router.get("/{merchant_id}/reviews")
def list_merchant_reviews(
    merchant_id: str, db: Session = Depends(get_db_session)
) -> dict[str, Any]:
    """Retrieve all customer reviews for a specific merchant."""
    stmt = select(Review).where(Review.merchant_id == merchant_id).order_by(Review.created_at.desc())
    rows = list(db.execute(stmt).scalars().all())
    return {
        "merchant_id": merchant_id,
        "count": len(rows),
        "reviews": [
            {
                "review_id": r.review_id,
                "rating": float(r.rating) if r.rating is not None else 5.0,
                "text": r.text,
                "sentiment": r.sentiment or "neutral",
                "total_like": r.total_like or 0,
                "source_kind": r.source_kind,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.get("/{merchant_id}/menu")
def list_merchant_menu(
    merchant_id: str, db: Session = Depends(get_db_session)
) -> dict[str, Any]:
    """Retrieve full menu items for a specific merchant."""
    stmt = select(MenuItem).where(MenuItem.merchant_id == merchant_id).order_by(MenuItem.category, MenuItem.name)
    rows = list(db.execute(stmt).scalars().all())
    return {
        "merchant_id": merchant_id,
        "count": len(rows),
        "menu_items": [
            {
                "item_id": m.item_id,
                "name": m.name,
                "price": m.price,
                "discount_price": m.discount_price,
                "description": m.description,
                "category": m.category or "Món chính",
                "image_url": m.image_url,
                "total_like": m.total_like or 0,
                "is_available": m.is_available,
            }
            for m in rows
        ],
    }


@router.get("/policies/processed")
def list_processed_policies(
    db: Session = Depends(get_db_session)
) -> dict[str, Any]:
    """Retrieve all processed policy documents formatted in canonical markdown."""
    stmt = select(PolicyDocument).order_by(PolicyDocument.document_id)
    rows = list(db.execute(stmt).scalars().all())
    return {
        "count": len(rows),
        "documents": [
            {
                "document_id": p.document_id,
                "title": p.title,
                "category": p.category,
                "source_url": p.source_url,
                "document_text": p.document_text,
                "policy_updated_at": p.policy_updated_at.isoformat() if p.policy_updated_at else None,
            }
            for p in rows
        ],
    }


@router.get("/{merchant_id}/evidence/{evidence_type}/{evidence_id}")
def get_evidence(merchant_id: str, evidence_type: str, evidence_id: str) -> object:
    return not_implemented("GET /api/v1/merchants/{id}/evidence/{type}/{id}")
