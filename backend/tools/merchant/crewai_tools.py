"""Native CrewAI BaseTool Wrappers (Design §4.1, §5.1, §9.1) — Merchant Vertical Tools.

Adheres strictly to CrewAI BaseTool class convention matching custom_tool.py reference.
"""
from __future__ import annotations

import json
from typing import Type, Any
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

from database.connection import SessionLocal
from repositories.merchant_profile_repository import MerchantProfileRepository
from repositories.evidence_repository import EvidenceRepository
from services.merchant_profile_service import MerchantProfileService
from services.recommendation_service import RecommendationService
from services.competitor_service import CompetitorService


# --- Tool 1: GetMerchantProfileTool ---
class GetMerchantProfileInput(BaseModel):
    merchant_id: str = Field(..., description="Target merchant ID to retrieve 8-dimension profile.")


class GetMerchantProfileTool(BaseTool):
    name: str = "get_merchant_profile"
    description: str = (
        "Retrieve 8-dimension performance profile for a merchant. "
        "Strictly obeys Security Rule C2: overall_score is stripped."
    )
    args_schema: Type[BaseModel] = GetMerchantProfileInput

    def _run(self, merchant_id: str) -> str:
        db = SessionLocal()
        try:
            svc = MerchantProfileService(db)
            profile = svc.get_profile_view(merchant_id)
            return json.dumps(profile, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"merchant_id": merchant_id, "error": str(e)}, ensure_ascii=False)
        finally:
            db.close()


# --- Tool 2: GetProfileEvidenceTool ---
class GetProfileEvidenceInput(BaseModel):
    merchant_id: str = Field(..., description="Target merchant ID")
    dimension: str | None = Field(None, description="Optional specific dimension name (e.g. 'waiting_time', 'food_quality')")


class GetProfileEvidenceTool(BaseTool):
    name: str = "get_profile_evidence"
    description: str = (
        "Retrieve evidence breakdown and supporting records (reviews, metrics, feedbacks) for a merchant profile."
    )
    args_schema: Type[BaseModel] = GetProfileEvidenceInput

    def _run(self, merchant_id: str, dimension: str | None = None) -> str:
        db = SessionLocal()
        try:
            profile_repo = MerchantProfileRepository(db)
            evidence_repo = EvidenceRepository(db)

            profile = profile_repo.get_profile(merchant_id)
            if not profile:
                return json.dumps({"merchant_id": merchant_id, "status": "not_found"}, ensure_ascii=False)

            dims = profile.get("dimensions", {})
            if dimension and dimension in dims:
                dim_data = dims[dimension]
                refs = dim_data.get("evidence_refs", [])
                evidences = evidence_repo.get_evidence_by_refs(refs)
                return json.dumps({
                    "merchant_id": merchant_id,
                    "dimension": dimension,
                    "details": dim_data,
                    "evidences": evidences,
                }, ensure_ascii=False)

            return json.dumps({
                "merchant_id": merchant_id,
                "dimensions": dims,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"merchant_id": merchant_id, "error": str(e)}, ensure_ascii=False)
        finally:
            db.close()


# --- Tool 3: DiagnoseMerchantTool ---
class DiagnoseMerchantInput(BaseModel):
    merchant_id: str = Field(..., description="Target merchant ID to diagnose operational weaknesses.")


class DiagnoseMerchantTool(BaseTool):
    name: str = "diagnose_merchant"
    description: str = (
        "Analyze merchant 8-dimension scores to identify root causes of underperformance (< 6.0/10). "
        "Returns max 5 root causes, each backed by evidence_refs."
    )
    args_schema: Type[BaseModel] = DiagnoseMerchantInput

    def _run(self, merchant_id: str) -> str:
        db = SessionLocal()
        try:
            rec_svc = RecommendationService(db)
            result = rec_svc.generate_recommendations(merchant_id)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"merchant_id": merchant_id, "error": str(e)}, ensure_ascii=False)
        finally:
            db.close()


# --- Tool 4: RecommendImprovementsTool ---
class RecommendImprovementsInput(BaseModel):
    merchant_id: str = Field(..., description="Target merchant ID to generate improvement actions.")


class RecommendImprovementsTool(BaseTool):
    name: str = "recommend_improvements"
    description: str = (
        "Generate evidence-backed actionable improvement steps for a merchant."
    )
    args_schema: Type[BaseModel] = RecommendImprovementsInput

    def _run(self, merchant_id: str) -> str:
        db = SessionLocal()
        try:
            rec_svc = RecommendationService(db)
            result = rec_svc.generate_recommendations(merchant_id)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"merchant_id": merchant_id, "error": str(e)}, ensure_ascii=False)
        finally:
            db.close()


# --- Tool 5: CompareCompetitorsTool ---
class CompareCompetitorsInput(BaseModel):
    merchant_id: str = Field(..., description="Target merchant ID")
    radius_km: float = Field(5.0, description="Search radius in kilometers")
    limit: int = Field(5, description="Maximum number of competitors to return")


class CompareCompetitorsTool(BaseTool):
    name: str = "compare_competitors"
    description: str = (
        "Compare a merchant's 8 dimensions with nearby competitor merchants in the same cuisine segment. "
        "Strictly limits output to top 5 competitors to keep prompt size token-efficient."
    )
    args_schema: Type[BaseModel] = CompareCompetitorsInput

    def _run(self, merchant_id: str, radius_km: float = 5.0, limit: int = 5) -> str:
        db = SessionLocal()
        try:
            safe_limit = min(max(1, limit), 5)
            comp_svc = CompetitorService(db)
            result = comp_svc.analyze_competitors(merchant_id, radius_km=radius_km, limit=safe_limit)

            light_competitors = []
            for c in result.get("competitors", []):
                dims_summary = {k: v.get("score") for k, v in c.get("dimensions", {}).items() if isinstance(v, dict)}
                light_competitors.append({
                    "merchant_id": c.get("merchant_id"),
                    "name": c.get("name"),
                    "cuisine": c.get("cuisine"),
                    "distance_km": c.get("distance_km"),
                    "dimension_scores": dims_summary,
                })

            return json.dumps({
                "target_merchant_id": result.get("target_merchant_id"),
                "target_name": result.get("target_name"),
                "cuisine": result.get("cuisine"),
                "radius_km": result.get("radius_km"),
                "competitor_count": len(light_competitors),
                "top_competitors": light_competitors,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"merchant_id": merchant_id, "error": str(e)}, ensure_ascii=False)
        finally:
            db.close()
