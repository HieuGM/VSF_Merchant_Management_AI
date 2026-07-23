"""Operational Metrics Tool (Task 2).

Fetches operational performance data: prep time, cancel rate, on-time rate, etc.
"""
from __future__ import annotations

import json
from typing import Any, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import OperationalMetric


def get_merchant_operational_metrics(
    merchant_id: str,
    db: Session | None = None,
) -> dict[str, Any]:
    """Return operational performance metrics for a merchant.

    Args:
        merchant_id: Target merchant ID.
        db: Optional injected DB session (for testing).

    Returns:
        dict with status, merchant_id, metrics dict (None values excluded).
    """
    session = db or SessionLocal()
    try:
        om: OperationalMetric | None = (
            session.query(OperationalMetric)
            .filter(OperationalMetric.merchant_id == merchant_id)
            .first()
        )
        if not om:
            return {"status": "not_found", "merchant_id": merchant_id, "metrics": {}}

        def _f(v: Any) -> float | None:
            return float(v) if v is not None else None

        metrics: dict[str, Any] = {}
        if om.avg_prep_time_min is not None:
            metrics["avg_prep_time_min"] = _f(om.avg_prep_time_min)
        if om.cancel_rate is not None:
            metrics["cancel_rate"] = _f(om.cancel_rate)
        if om.acceptance_rate is not None:
            metrics["acceptance_rate"] = _f(om.acceptance_rate)
        if om.on_time_rate is not None:
            metrics["on_time_rate"] = _f(om.on_time_rate)
        if om.avg_delivery_time_min is not None:
            metrics["avg_delivery_time_min"] = _f(om.avg_delivery_time_min)
        if om.driver_rating is not None:
            metrics["driver_rating"] = _f(om.driver_rating)
        if om.packaging_ok_rate is not None:
            metrics["packaging_ok_rate"] = _f(om.packaging_ok_rate)
        if om.estimated_daily_orders is not None:
            metrics["estimated_daily_orders"] = om.estimated_daily_orders
        if om.peak_hours:
            metrics["peak_hours"] = list(om.peak_hours)

        return {
            "status": "ok",
            "merchant_id": merchant_id,
            "metrics": metrics,
        }
    finally:
        if db is None:
            session.close()


# --- CrewAI Tool Class ---

class GetMerchantOperationalMetricsInput(BaseModel):
    merchant_id: str = Field(..., description="Merchant ID to look up operational metrics for.")


class GetMerchantOperationalMetricsTool(BaseTool):
    name: str = "get_merchant_operational_metrics"
    description: str = (
        "Fetch operational performance metrics for a specific merchant: "
        "avg_prep_time_min, cancel_rate, acceptance_rate, on_time_rate, "
        "avg_delivery_time_min, driver_rating, packaging_ok_rate, estimated_daily_orders, peak_hours. "
        "Only populated fields are returned."
    )
    args_schema: Type[BaseModel] = GetMerchantOperationalMetricsInput

    def _run(self, merchant_id: str) -> str:
        res = get_merchant_operational_metrics(merchant_id=merchant_id)
        return json.dumps(res, ensure_ascii=False)
