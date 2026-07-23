"""Merchant Profile + search contracts (design §6.4, §11.2).

FROZEN SEAM (owner: Dev B, but consumed cross-domain via get_merchant_profile tool).
`overall_score` is stored but MUST be stripped from external surfaces (§6.4 [C2]).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# The eight scored dimensions — design §6.4. Order is contract.
SCORED_DIMENSIONS: tuple[str, ...] = (
    "food_quality",
    "image_quality",
    "delivery_quality",
    "packaging",
    "service",
    "waiting_time",
    "menu_diversity",
    "price_competitiveness",
)

PROFILE_SCHEMA_VERSION = "2.0"


class Evidence(BaseModel):
    evidence_id: str
    type: str
    value: Any
    unit: str | None = None
    ref_type: str | None = None
    ref_ids: list[str] = Field(default_factory=list)
    source_kind: str  # real | synthetic | heuristic


class DimensionScore(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    basis: str


class MerchantSearchItem(BaseModel):
    """§11.2 search result item."""

    merchant_id: str
    name: str
    cuisine: str
    city: str
    price_level: str | None = None
    rating: float | None = None
    distance_km: float | None = None
    lat: float | None = None
    lng: float | None = None
    source: str = "internal_catalog"


class MerchantProfilePublic(BaseModel):
    """External profile surface — NO overall_score (§6.4 [C2]).

    `dimensions` maps each of SCORED_DIMENSIONS to a DimensionScore. Kept as dict so the
    scoring engine owns the exact values; presence of all 8 keys is validated downstream.
    """

    merchant_id: str
    tier: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    price_level: str | None = None
    dimensions: dict[str, DimensionScore] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)
    ratings: dict[str, Any] = Field(default_factory=dict)
    schema_version: str = PROFILE_SCHEMA_VERSION
    updated_at: str | None = None
