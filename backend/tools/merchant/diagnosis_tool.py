"""Merchant diagnosis & recommendation tools (F-02 Merchant) — Evidence-backed diagnosis & recommendations.

Rule: Causes capped at max 5, each cause MUST have at least 1 evidence_ref.
"""
from __future__ import annotations

from typing import Any
from sqlalchemy.orm import Session
from database.connection import SessionLocal
from repositories.merchant_profile_repository import MerchantProfileRepository
from repositories.evidence_repository import EvidenceRepository
from tools.allow_list import agents_allowed_for
from tools.registry import ToolRegistry, ToolSpec


def diagnose_merchant(
    merchant_id: str, db: Session | None = None
) -> dict[str, Any]:
    """Analyze merchant 8-dimension scores to identify root causes of underperformance (< 6.0/10).

    Returns:
        Structured diagnosis with max 5 root causes, each backed by evidence_refs.
    """
    session = db or SessionLocal()
    try:
        profile_repo = MerchantProfileRepository(session)
        evidence_repo = EvidenceRepository(session)

        profile = profile_repo.get_profile(merchant_id)
        if not profile:
            return {"merchant_id": merchant_id, "status": "insufficient_data", "causes": []}

        dims = profile.get("dimensions", {})
        causes: list[dict[str, Any]] = []

        for dim_name, dim_data in dims.items():
            if not isinstance(dim_data, dict):
                continue

            score = dim_data.get("score", 10.0)
            if score < 6.0:
                refs = dim_data.get("evidence_refs", [])
                if not refs:
                    refs = [f"METRIC-{merchant_id}"]

                evidences = evidence_repo.get_evidence_by_refs(refs)

                causes.append({
                    "dimension": dim_name,
                    "score": score,
                    "issue": f"Điểm {dim_name} thấp ({score}/10) — {dim_data.get('basis', '')}",
                    "evidence_refs": refs,
                    "evidences": evidences,
                })

        causes = causes[:5]
        status = "ok" if causes else "healthy"

        return {
            "merchant_id": merchant_id,
            "status": status,
            "causes": causes,
        }
    finally:
        if db is None:
            session.close()


def recommend_improvements(
    merchant_id: str, db: Session | None = None
) -> dict[str, Any]:
    """Generate evidence-backed actionable improvement steps based on diagnostic causes.

    Returns:
        Structured improvement actions mapped to evidence references.
    """
    diag = diagnose_merchant(merchant_id, db=db)
    causes = diag.get("causes", [])
    actions: list[dict[str, Any]] = []

    for cause in causes:
        dim = cause["dimension"]
        score = cause["score"]

        action_title = f"Cải thiện chỉ số {dim.replace('_', ' ').capitalize()}"
        description = (
            f"Điểm hiện tại: {score}/10. Khuyến nghị tối ưu quy trình và giải quyết các "
            f"phản hồi từ chứng cứ {cause['evidence_refs']}."
        )

        actions.append({
            "dimension": dim,
            "action_title": action_title,
            "description": description,
            "expected_impact": "Tăng điểm đánh giá & cải thiện trải nghiệm khách hàng",
            "evidence_refs": cause["evidence_refs"],
        })

    return {
        "merchant_id": merchant_id,
        "status": diag.get("status", "healthy"),
        "actions": actions,
    }


def register(reg: ToolRegistry) -> None:
    """Auto-discovery entry point for diagnosis & recommendation tools."""
    reg.register(
        ToolSpec(
            name="diagnose_merchant",
            description="Analyze merchant weaknesses and return evidence-backed root causes.",
            input_schema={"merchant_id": "str"},
            output_schema={"merchant_id": "str", "status": "str", "causes": "list"},
            allowed_agents=agents_allowed_for("diagnose_merchant"),
            cache_policy="profile_snapshot",
            source_kind="real",
        ),
        diagnose_merchant,
    )
    reg.register(
        ToolSpec(
            name="recommend_improvements",
            description="Generate evidence-backed improvement actions based on merchant diagnosis.",
            input_schema={"merchant_id": "str"},
            output_schema={"merchant_id": "str", "status": "str", "actions": "list"},
            allowed_agents=agents_allowed_for("recommend_improvements"),
            cache_policy="profile_snapshot",
            source_kind="real",
        ),
        recommend_improvements,
    )
