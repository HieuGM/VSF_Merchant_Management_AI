"""Evidence Repository (C-02) — Data access layer for resolving evidence references.

Resolves evidence refs across reviews, operational_metrics, and delivery_feedbacks.
"""
from __future__ import annotations

from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import Review, OperationalMetric, DeliveryFeedback


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

            if ref.startswith("REV-"):
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
                        "avg_prep_time_min": metric.avg_prep_time_min,
                        "peak_hours": metric.peak_hours,
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
