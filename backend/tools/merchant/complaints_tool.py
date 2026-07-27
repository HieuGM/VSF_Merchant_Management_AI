"""Complaints Tool (Task 3).

Fetches complaint summary for a merchant, grouped by category and severity.
Returns aggregated counts + sample text (no raw personal data).
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Optional, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import MerchantComplaint

# Valid complaint categories per DB CHECK constraint
COMPLAINT_CATEGORIES = [
    "giao_hàng_trễ",
    "món_nguội",
    "sai_hoặc_thiếu_món",
    "đóng_gói_kém",
    "thái_độ_phục_vụ",
    "giá_cao",
    "vệ_sinh",
    "chất_lượng_món",
]

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def get_merchant_complaints(
    merchant_id: str,
    category: str | None = None,
    severity: str | None = None,
    limit_samples: int = 3,
    db: Session | None = None,
) -> dict[str, Any]:
    """Return complaint summary for a merchant, grouped by category.

    Args:
        merchant_id: Target merchant ID.
        category: Optional filter by category (e.g. 'giao_hàng_trễ').
        severity: Optional filter by severity: 'high', 'medium', 'low'.
        limit_samples: Max complaint text samples per category to include (default 3).
        db: Optional injected DB session.

    Returns:
        dict with status, total_count, by_category breakdown, and summary.
    """
    session = db or SessionLocal()
    try:
        query = session.query(MerchantComplaint).filter(
            MerchantComplaint.merchant_id == merchant_id
        )
        if category:
            query = query.filter(MerchantComplaint.category == category.strip())
        if severity:
            query = query.filter(MerchantComplaint.severity == severity.strip())

        complaints = query.order_by(
            MerchantComplaint.occurred_on.desc().nulls_last()
        ).all()

        if not complaints:
            return {
                "status": "ok",
                "merchant_id": merchant_id,
                "total_count": 0,
                "by_category": {},
                "summary": "No complaints found.",
            }

        # Aggregate
        cat_data: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "severity_counts": {"high": 0, "medium": 0, "low": 0}, "samples": []}
        )
        for c in complaints:
            cat = c.category
            cat_data[cat]["count"] += 1
            cat_data[cat]["severity_counts"][c.severity] += 1
            if len(cat_data[cat]["samples"]) < limit_samples:
                cat_data[cat]["samples"].append(c.text[:200])  # Truncate long texts

        # Sort by count descending
        sorted_cats = sorted(cat_data.items(), key=lambda kv: kv[1]["count"], reverse=True)
        by_category = {k: v for k, v in sorted_cats}

        top_issues = [
            f"{k} ({v['count']} lần, {sum(v['severity_counts'].values())} total)"
            for k, v in sorted_cats[:3]
        ]
        summary = "Top issues: " + "; ".join(top_issues) if top_issues else "No significant issues."

        return {
            "status": "ok",
            "merchant_id": merchant_id,
            "total_count": len(complaints),
            "by_category": by_category,
            "summary": summary,
        }
    finally:
        if db is None:
            session.close()


# --- CrewAI Tool Class ---

from typing import Literal

SeverityLevel = Literal["low", "medium", "high"]


class GetMerchantComplaintsInput(BaseModel):
    merchant_id: str = Field(..., description="Target merchant ID to fetch customer complaints for.")
    category: Optional[str] = Field(
        None,
        description=(
            "Optional category filter keyword (e.g., "
            "'giao_hàng_trễ', 'món_nguội', 'sai_hoặc_thiếu_món', 'đóng_gói_kém', "
            "'thái_độ_phục_vụ', 'chất_lượng_món'). Leave empty for all categories."
        ),
    )
    severity: Optional[SeverityLevel] = Field(
        None,
        description="Optional severity level filter: 'high', 'medium', or 'low'.",
    )
    limit_samples: int = Field(3, description="Max complaint text samples per category (1..5).")


class GetMerchantComplaintsTool(BaseTool):
    name: str = "get_merchant_complaints"
    description: str = (
        "Fetch aggregated complaint data for a merchant, grouped by category. "
        "Returns total count, per-category breakdown with severity counts, "
        "and sample complaint texts. Use category/severity filters to focus analysis."
    )
    args_schema: Type[BaseModel] = GetMerchantComplaintsInput

    def _run(
        self,
        merchant_id: str,
        category: str | None = None,
        severity: str | None = None,
        limit_samples: int = 3,
    ) -> str:
        res = get_merchant_complaints(
            merchant_id=merchant_id,
            category=category,
            severity=severity,
            limit_samples=max(1, min(limit_samples, 5)),
        )
        return json.dumps(res, ensure_ascii=False)
