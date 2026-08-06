"""Evidence Repository (C-02) — Data access layer for resolving evidence references.

Resolves evidence refs across reviews, operational_metrics, and delivery_feedbacks.
"""
from __future__ import annotations

from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import (
    DeliveryFeedback,
    FoodImage,
    MerchantComplaint,
    MerchantDimensionEvidence,
    MerchantProfile,
    OperationalMetric,
    Review,
)


_PROFILE_COLUMNS = {
    "food_quality": "food_quality_score",
    "image_quality": "image_quality_score",
    "delivery_quality": "delivery_quality_score",
    "packaging": "packaging_score",
    "service": "service_score",
    "waiting_time": "waiting_time_score",
    "menu_diversity": "menu_diversity_score",
    "price_competitiveness": "price_competitiveness_score",
}


class EvidenceRepository:
    """Repository for resolving evidence reference IDs to underlying record details."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_evidence_by_refs(self, refs: list[str]) -> list[dict[str, Any]]:
        """Resolve a list of evidence ref IDs (e.g. ['REV-101', 'METRIC-m123']) to details."""
        results: list[dict[str, Any]] = []

        for ref in refs:
            if not ref:
                continue

            typed = self._db.get(MerchantDimensionEvidence, ref)
            if typed is not None:
                if typed.value_numeric is not None:
                    value = float(typed.value_numeric)
                elif typed.value_text is not None:
                    value = typed.value_text
                else:
                    value = typed.value_boolean
                results.append(
                    {
                        "ref": ref,
                        "type": typed.evidence_type,
                        "dimension": typed.dimension,
                        "value": value,
                        "unit": typed.unit,
                        "ref_ids": list(typed.reference_ids or []),
                        "source_kind": typed.source_kind,
                    }
                )
            elif ref.startswith("REV-"):
                rev_id = ref.replace("REV-", "", 1)
                review = self._db.get(Review, ref) or self._db.get(Review, rev_id)
                if review:
                    results.append({
                        "ref": ref,
                        "type": "review",
                        "content": review.text,
                        "rating": review.rating,
                        "created_at": str(review.created_at) if review.created_at else None,
                    })

            elif ref.startswith("METRIC-"):
                merchant_id = ref.replace("METRIC-", "", 1)
                metric = self._db.get(OperationalMetric, merchant_id)
                if metric:
                    results.append({
                        "ref": ref,
                        "type": "operational_metric",
                        "avg_prep_time_min": (
                            float(metric.avg_prep_time_min)
                            if metric.avg_prep_time_min is not None
                            else None
                        ),
                        "peak_hours": list(metric.peak_hours or []),
                    })

            elif ref.startswith("FB-"):
                fb_id = ref.replace("FB-", "", 1)
                feedback = self._db.get(DeliveryFeedback, ref) or self._db.get(DeliveryFeedback, fb_id)
                if feedback:
                    results.append({
                        "ref": ref,
                        "type": "delivery_feedback",
                        "rating": feedback.rating,
                        "comment": feedback.comment,
                    })

        return results

    def resolve_reference(
        self,
        ref: str,
        aggregate_snapshots: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Resolve the typed reference formats used by runtime claim validation."""
        typed = self._db.get(MerchantDimensionEvidence, ref)
        if typed is not None:
            value = (
                float(typed.value_numeric)
                if typed.value_numeric is not None
                else typed.value_text
                if typed.value_text is not None
                else typed.value_boolean
            )
            return {
                "ref": ref,
                "type": "dimension_evidence",
                "merchant_id": typed.merchant_id,
                "dimension": typed.dimension,
                "field": typed.evidence_type,
                "value": value,
            }

        parts = ref.split(":")
        kind = parts[0] if parts else ""
        if kind == "review" and len(parts) == 2:
            row = self._db.get(Review, parts[1])
            if row:
                return {
                    "ref": ref,
                    "type": "review",
                    "merchant_id": row.merchant_id,
                    "field": "rating",
                    "value": float(row.rating) if row.rating is not None else None,
                    "text": row.text,
                }
        if kind == "complaint" and len(parts) == 2:
            row = self._db.get(MerchantComplaint, parts[1])
            if row:
                return {
                    "ref": ref,
                    "type": "complaint",
                    "merchant_id": row.merchant_id,
                    "field": "text",
                    "value": row.text,
                }
        if kind == "metric" and len(parts) == 3:
            merchant_id, field = parts[1], parts[2]
            row = self._db.get(OperationalMetric, merchant_id)
            if row is not None and hasattr(row, field):
                value = getattr(row, field)
                return {
                    "ref": ref,
                    "type": "operational_metric",
                    "merchant_id": merchant_id,
                    "field": field,
                    "value": float(value) if value is not None else None,
                }
        if kind == "profile" and len(parts) == 3:
            merchant_id, dimension = parts[1], parts[2]
            column = _PROFILE_COLUMNS.get(dimension)
            row = self._db.get(MerchantProfile, merchant_id)
            if row is not None and column:
                return {
                    "ref": ref,
                    "type": "profile",
                    "merchant_id": merchant_id,
                    "dimension": dimension,
                    "field": dimension,
                    "value": float(getattr(row, column)),
                }
        if kind == "image" and len(parts) == 2:
            row = self._db.get(FoodImage, parts[1])
            if row:
                return {
                    "ref": ref,
                    "type": "image",
                    "merchant_id": row.merchant_id,
                    "field": "dish_image_quality",
                    "value": (
                        float(row.dish_image_quality)
                        if row.dish_image_quality is not None
                        else None
                    ),
                    "url": row.url,
                }
        if kind == "aggregate" and len(parts) >= 3:
            step_id = parts[1]
            path = ":".join(parts[2:])
            snapshot = (aggregate_snapshots or {}).get(step_id)
            if snapshot is None:
                return None
            value: Any = snapshot
            path_parts = path.split(".")
            if path_parts[0] not in value and isinstance(value.get("aggregates"), dict):
                value = value["aggregates"]
            for path_part in path_parts:
                if not isinstance(value, dict) or path_part not in value:
                    return None
                value = value[path_part]
            return {
                "ref": ref,
                "type": "aggregate",
                "merchant_id": None,
                "field": path,
                "value": value,
                "step_id": step_id,
            }
        return None
