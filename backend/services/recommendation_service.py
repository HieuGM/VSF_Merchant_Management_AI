"""Recommendation Service (C-05) — Business logic layer for generating evidence-backed recommendations.
"""
from __future__ import annotations

from typing import Any
from sqlalchemy.orm import Session
from repositories.merchant_profile_repository import MerchantProfileRepository
from repositories.evidence_repository import EvidenceRepository


class RecommendationService:
    """Service layer for deterministic diagnosis and recommendation generation."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._profile_repo = MerchantProfileRepository(db)
        self._evidence_repo = EvidenceRepository(db)

    def generate_recommendations(self, merchant_id: str) -> dict[str, Any]:
        """Generate structured improvement recommendations backed by evidence references."""
        profile = self._profile_repo.get_profile(merchant_id)
        if not profile:
            return {"merchant_id": merchant_id, "status": "insufficient_data", "actions": []}

        dims = profile.get("dimensions", {})
        actions: list[dict[str, Any]] = []

        for dim_name, dim_data in dims.items():
            if not isinstance(dim_data, dict):
                continue

            score = dim_data.get("score", 1.0)
            if score < 0.6:
                refs = dim_data.get("evidence_refs", [])
                if not refs:
                    continue

                evidences = self._evidence_repo.get_evidence_by_refs(refs)

                actions.append({
                    "dimension": dim_name,
                    "action_title": f"Tối ưu chỉ số {dim_name.replace('_', ' ').capitalize()}",
                    "current_score": score,
                    "target_score": min(1.0, round(score + 0.15, 3)),
                    "description": (
                        f"Điểm hiện tại ({score:.3f}) thấp hơn ngưỡng kỳ vọng 0.600. "
                        f"Khuyến nghị xử lý dựa trên {len(evidences)} chứng cứ phản hồi."
                    ),
                    "expected_impact": "Tăng 15-20% đánh giá tích cực từ khách hàng",
                    "evidence_refs": refs,
                    "evidences": evidences,
                })

        return {
            "merchant_id": merchant_id,
            "status": "ok" if actions else "healthy",
            "actions": actions,
        }
