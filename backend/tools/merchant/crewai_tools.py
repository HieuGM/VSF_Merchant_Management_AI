"""CrewAI Tool Registry — Merchant Vertical (Task 5 wiring).

Exports all tool instances that agents can use.
All tools are thin wrappers that delegate to pure functions in their respective modules.
"""
from __future__ import annotations

from tools.merchant.helper_tool import GetMerchantMetadataCatalogTool
from tools.merchant.search_tool import SearchMerchantsTool, SearchTrendingDishesTool
from tools.merchant.profile_tool import GetMerchantProfileSummaryTool
from tools.merchant.metrics_tool import GetMerchantOperationalMetricsTool
from tools.merchant.complaints_tool import GetMerchantComplaintsTool
from tools.merchant.menu_image_tool import GetMenuAndFoodImagesTool
from tools.merchant.competitor_tool import CompareMerchantBenchmarkTool

# Legacy diagnosis / recommendation tools (kept from original)
from tools.merchant.diagnosis_tool import diagnose_merchant, recommend_improvements
import json
from typing import Type, Any
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from database.connection import SessionLocal


# --- DiagnoseMerchantTool (kept for backward compat) ---
class DiagnoseMerchantInput(BaseModel):
    merchant_id: str = Field(..., description="Target merchant ID to diagnose operational weaknesses.")


class DiagnoseMerchantTool(BaseTool):
    name: str = "diagnose_merchant"
    description: str = (
        "Analyze merchant 8-dimension scores to identify root causes of underperformance (< 0.6). "
        "Returns max 5 root causes, each backed by evidence_refs."
    )
    args_schema: Type[BaseModel] = DiagnoseMerchantInput

    def _run(self, merchant_id: str) -> str:
        db = SessionLocal()
        try:
            result = diagnose_merchant(merchant_id, db=db)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"merchant_id": merchant_id, "error": str(e)}, ensure_ascii=False)
        finally:
            db.close()


# --- RecommendImprovementsTool (kept for backward compat) ---
class RecommendImprovementsInput(BaseModel):
    merchant_id: str = Field(..., description="Target merchant ID to generate improvement actions.")


class RecommendImprovementsTool(BaseTool):
    name: str = "recommend_improvements"
    description: str = "Generate evidence-backed actionable improvement steps for a merchant."
    args_schema: Type[BaseModel] = RecommendImprovementsInput

    def _run(self, merchant_id: str) -> str:
        db = SessionLocal()
        try:
            result = recommend_improvements(merchant_id, db=db)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"merchant_id": merchant_id, "error": str(e)}, ensure_ascii=False)
        finally:
            db.close()


# ── Tool Catalog ─────────────────────────────────────────────────────────────
# Instantiated singletons — agents should import from here.

merchant_tools = [
    GetMerchantMetadataCatalogTool(),
    SearchMerchantsTool(),
    SearchTrendingDishesTool(),
    GetMerchantProfileSummaryTool(),
    GetMerchantOperationalMetricsTool(),
    GetMerchantComplaintsTool(),
    GetMenuAndFoodImagesTool(),
    CompareMerchantBenchmarkTool(),
    DiagnoseMerchantTool(),
    RecommendImprovementsTool(),
]

__all__ = [
    "merchant_tools",
    "GetMerchantMetadataCatalogTool",
    "SearchMerchantsTool",
    "SearchTrendingDishesTool",
    "GetMerchantProfileSummaryTool",
    "GetMerchantOperationalMetricsTool",
    "GetMerchantComplaintsTool",
    "GetMenuAndFoodImagesTool",
    "CompareMerchantBenchmarkTool",
    "DiagnoseMerchantTool",
    "RecommendImprovementsTool",
]
