"""Evidence Repository (C-02) — Data access layer for resolving evidence references.

Resolves evidence refs across reviews, operational_metrics, and delivery_feedbacks.
"""
from __future__ import annotations

from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import (
    DeliveryFeedback,
    MerchantDimensionEvidence,
    OperationalMetric,
    Review,
)


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

    def get_dimension_evidence(
        self, merchant_id: str, dimension: str
    ) -> list[dict[str, Any]]:
        rows = self._db.execute(
            select(MerchantDimensionEvidence)
            .where(
                MerchantDimensionEvidence.merchant_id == merchant_id,
                MerchantDimensionEvidence.dimension == dimension,
            )
            .order_by(MerchantDimensionEvidence.evidence_id)
        ).scalars()
        return [
            {
                "evidence_id": row.evidence_id,
                "type": row.evidence_type,
                "value": (
                    float(row.value_numeric)
                    if row.value_numeric is not None
                    else row.value_text
                    if row.value_text is not None
                    else row.value_boolean
                ),
                "unit": row.unit,
                "ref_type": row.reference_type,
                "ref_ids": list(row.reference_ids or []),
                "source_kind": row.source_kind,
            }
            for row in rows
        ]
