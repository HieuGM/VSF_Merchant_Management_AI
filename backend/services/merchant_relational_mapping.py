"""Canonical mapping from legacy profile objects to relational current-state rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


DIMENSIONS: tuple[str, ...] = (
    "food_quality",
    "image_quality",
    "delivery_quality",
    "packaging",
    "service",
    "waiting_time",
    "menu_diversity",
    "price_competitiveness",
)

LEGACY_DIMENSION_NAMES = {
    "price_competitiveness": "price_level",
}

_SOURCE_KINDS = {
    "real",
    "synthetic",
    "heuristic",
    "mixed",
    "development_fixture",
}


@dataclass(frozen=True)
class MappedMerchantData:
    profile: dict[str, Any]
    ratings: dict[str, Any]
    operations: dict[str, Any]
    calculations: list[dict[str, Any]]
    evidence: list[dict[str, Any]]


def _decimal(value: Any, *, field: str, places: str | None = None) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric, got {value!r}") from exc
    if places:
        result = result.quantize(Decimal(places), rounding=ROUND_HALF_UP)
    return result


def _score(value: Any, dimension: str) -> Decimal:
    result = _decimal(value, field=f"{dimension} score", places="0.001")
    if not Decimal("0") <= result <= Decimal("1"):
        raise ValueError(f"{dimension} score must be between 0 and 1")
    return result


def _typed_value(value: Any) -> tuple[str, Any]:
    if isinstance(value, bool):
        return "value_boolean", value
    if isinstance(value, (int, float, Decimal)):
        return "value_numeric", _decimal(value, field="evidence value")
    if isinstance(value, str):
        return "value_text", value
    raise ValueError(f"unsupported evidence scalar: {value!r}")


def map_legacy_profile(
    merchant_id: str,
    legacy: dict[str, Any],
    *,
    source_kind: str = "mixed",
    calculated_at: datetime | None = None,
) -> MappedMerchantData:
    """Map one legacy profile into typed rows without writing to the database."""

    if source_kind not in _SOURCE_KINDS:
        raise ValueError(f"unsupported source_kind: {source_kind}")

    dimensions = legacy.get("dimensions")
    if not isinstance(dimensions, dict):
        raise ValueError(f"merchant {merchant_id} dimensions must be an object")

    missing = [
        legacy_name
        for legacy_name in ("food_quality", "image_quality", "delivery_quality",
                            "packaging", "service", "waiting_time",
                            "menu_diversity", "price_level")
        if legacy_name not in dimensions
    ]
    if missing:
        raise ValueError(f"missing dimensions: {', '.join(missing)}")

    calculated_at = calculated_at or datetime.now(timezone.utc)
    attributes = legacy.get("attributes") or {}
    operation_kpis = attributes.get("operation_kpis") or {}
    profile: dict[str, Any] = {
        "tier": legacy.get("tier") or "background",
        "price_level": legacy.get("price_level") or "trung bình",
        "scoring_version": legacy.get("scoring_version") or "1.0",
        "scored_at": calculated_at,
    }
    calculations: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []

    for dimension in DIMENSIONS:
        legacy_name = LEGACY_DIMENSION_NAMES.get(dimension, dimension)
        dim_data = dimensions[legacy_name]
        if not isinstance(dim_data, dict):
            raise ValueError(f"{legacy_name} dimension must be an object")

        score_value = dim_data.get("score")
        if dimension == "waiting_time" and operation_kpis.get("avg_prep_minutes") is not None:
            prep_minutes = _decimal(
                operation_kpis["avg_prep_minutes"],
                field="avg_prep_time_min",
            )
            score_value = max(
                Decimal("0"),
                min(Decimal("1"), Decimal("1") - (prep_minutes - Decimal("5")) / Decimal("40")),
            )
        profile[f"{dimension}_score"] = _score(score_value, dimension)
        calculations.append(
            {
                "merchant_id": merchant_id,
                "dimension": dimension,
                "basis": (
                    "avg_prep_time_min only"
                    if dimension == "waiting_time"
                    else str(dim_data.get("basis") or "unspecified")
                ),
                "source_kind": source_kind,
                "scoring_version": profile["scoring_version"],
                "calculated_at": calculated_at,
            }
        )

        for index, evidence in enumerate(dim_data.get("evidence") or []):
            if not isinstance(evidence, dict) or "type" not in evidence:
                raise ValueError(f"{dimension} evidence must contain type")
            evidence_type = str(evidence["type"])
            # M1: waiting_time is preparation time only.
            if dimension == "waiting_time" and evidence_type == "late_complaint_count":
                continue
            if "value" not in evidence:
                raise ValueError(f"{dimension}/{evidence_type} evidence must contain value")
            value_column, typed_value = _typed_value(evidence["value"])
            row = {
                "evidence_id": (
                    f"ev:{merchant_id}:{dimension}:{evidence_type}:{index}"
                ),
                "merchant_id": merchant_id,
                "dimension": dimension,
                "evidence_type": evidence_type,
                "value_numeric": None,
                "value_text": None,
                "value_boolean": None,
                "unit": evidence.get("unit"),
                "reference_type": evidence.get("ref_type"),
                "reference_ids": list(
                    evidence.get("ref_ids") or evidence.get("reference_ids") or []
                ),
                "source_kind": evidence.get("source_kind") or source_kind,
                "observed_at": evidence.get("observed_at"),
            }
            row[value_column] = typed_value
            evidence_rows.append(row)

    ratings_source = legacy.get("ratings") or {}
    ratings = {
        "shopeefood_rating": (
            _decimal(ratings_source["shopeefood_avg"], field="shopeefood_rating", places="0.01")
            if ratings_source.get("shopeefood_avg") is not None
            else None
        ),
        "shopeefood_review_count": ratings_source.get("shopeefood_total_review"),
        "foody_rating": (
            _decimal(ratings_source["foody_rating"], field="foody_rating", places="0.01")
            if ratings_source.get("foody_rating") is not None
            else None
        ),
        "foody_review_count": ratings_source.get("foody_review_count"),
    }

    delivery_stats = attributes.get("delivery_stats") or {}
    operations = {
        "avg_prep_time_min": (
            _decimal(operation_kpis["avg_prep_minutes"], field="avg_prep_time_min", places="0.01")
            if operation_kpis.get("avg_prep_minutes") is not None
            else None
        ),
        "cancel_rate": operation_kpis.get("cancel_rate"),
        "acceptance_rate": operation_kpis.get("acceptance_rate"),
        "estimated_daily_orders": operation_kpis.get("estimated_daily_orders"),
        "peak_hours": list(operation_kpis.get("peak_hours") or attributes.get("peak_time") or []),
        "avg_delivery_time_min": delivery_stats.get("avg_delivery_minutes"),
        "on_time_rate": delivery_stats.get("on_time_rate"),
        "driver_rating": delivery_stats.get("driver_rating"),
        "packaging_ok_rate": delivery_stats.get("packaging_ok_rate"),
        "source_kind": source_kind,
    }

    return MappedMerchantData(
        profile=profile,
        ratings=ratings,
        operations=operations,
        calculations=calculations,
        evidence=evidence_rows,
    )
