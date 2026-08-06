"""Code-enforced owner-private and competitor-public data policy."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.errors import ForbiddenError
from pydantic import BaseModel, Field


PUBLIC_DIMENSIONS: frozenset[str] = frozenset(
    {
        "food_quality",
        "image_quality",
        "menu_diversity",
        "price_competitiveness",
    }
)

PUBLIC_FIELDS: frozenset[str] = frozenset(
    {
        "status",
        "merchant_id",
        "name",
        "cuisine",
        "category",
        "city",
        "city_slug",
        "address",
        "lat",
        "lng",
        "price_level",
        "menu_price_min",
        "menu_price_median",
        "menu_price_max",
        "ratings",
        "rating",
        "review_count",
        "review_sentiment",
        "review_themes",
        "image_quality",
        "image_coverage",
        "tags",
        "dimensions",
        "distance_km",
        "is_active",
        "opens_at",
        "closes_at",
        "timezone",
        "menu_items",
    }
)

_PRIVATE_QUERY_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("revenue", ("doanh thu", "revenue")),
    (
        "estimated_daily_orders",
        ("số đơn", "đơn hàng nội bộ", "đơn mỗi ngày", "daily orders"),
    ),
    ("cancel_rate", ("tỷ lệ hủy", "tỷ lệ huỷ", "hủy đơn", "huỷ đơn")),
    ("acceptance_rate", ("tỷ lệ nhận đơn", "acceptance rate")),
    (
        "avg_prep_time",
        ("thời gian chuẩn bị", "prep time", "thời gian chế biến"),
    ),
    ("on_time_rate", ("tỷ lệ đúng giờ", "on-time rate")),
    (
        "delivery_operations",
        ("thời gian giao hàng nội bộ", "driver rating", "chỉ số giao hàng"),
    ),
    (
        "private_complaints",
        (
            "complaints riêng",
            "complaint riêng",
            "khiếu nại nội bộ",
            "phàn nàn nội bộ",
        ),
    ),
)

_OWNER_TARGET_TERMS: tuple[str, ...] = (
    "quán tôi",
    "quán của tôi",
    "quán mình",
    "cửa hàng tôi",
    "cửa hàng của tôi",
    "merchant của tôi",
)

_COMPETITOR_TARGET_TERMS: tuple[str, ...] = (
    "đối thủ",
    "quán khác",
    "nhà hàng khác",
    "từng đối thủ",
    "từng quán",
    "các quán khác",
)


class QueryPolicyDecision(BaseModel):
    allowed: bool
    scope: str
    private_fields: list[str] = Field(default_factory=list)
    reason: str | None = None


class MerchantDataPolicy:
    """Project records to the data surface allowed for the current run."""

    def __init__(self, owner_merchant_id: str) -> None:
        self.owner_merchant_id = str(owner_merchant_id)

    def assert_owner_target(self, target_merchant_id: str) -> None:
        if str(target_merchant_id) != self.owner_merchant_id:
            raise ForbiddenError(
                "Không được truy cập dữ liệu vận hành riêng của merchant khác.",
                details={
                    "owner_merchant_id": self.owner_merchant_id,
                    "target_merchant_id": str(target_merchant_id),
                },
            )

    def owner_private(
        self,
        target_merchant_id: str,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        self.assert_owner_target(target_merchant_id)
        return deepcopy(record)

    def competitor_public(self, record: dict[str, Any]) -> dict[str, Any]:
        projected = {
            key: deepcopy(value)
            for key, value in record.items()
            if key in PUBLIC_FIELDS
        }
        dimensions = record.get("dimensions")
        if isinstance(dimensions, dict):
            projected["dimensions"] = {
                key: deepcopy(value)
                for key, value in dimensions.items()
                if key in PUBLIC_DIMENSIONS
            }
        return projected

    def query_decision(
        self,
        query: str,
        *,
        targets_other_merchant: bool = False,
    ) -> QueryPolicyDecision:
        """Classify the requested data surface before planning any tool calls."""
        lowered = query.casefold()
        private_fields = [
            field
            for field, aliases in _PRIVATE_QUERY_FIELDS
            if any(alias in lowered for alias in aliases)
        ]
        targets_competitor = any(
            term in lowered for term in _COMPETITOR_TARGET_TERMS
        )
        targets_owner = any(term in lowered for term in _OWNER_TARGET_TERMS)

        if (targets_competitor or targets_other_merchant) and private_fields:
            return QueryPolicyDecision(
                allowed=False,
                scope="competitor_private",
                private_fields=private_fields,
                reason=(
                    "Không thể cung cấp dữ liệu riêng tư hoặc KPI vận hành nội bộ "
                    "của merchant khác. Tôi chỉ có thể dùng dữ liệu công khai để "
                    "tìm kiếm, phân tích cohort và so sánh chất lượng."
                ),
            )
        if targets_owner:
            return QueryPolicyDecision(
                allowed=True,
                scope="owner_private",
                private_fields=private_fields,
            )
        if targets_competitor:
            return QueryPolicyDecision(
                allowed=True,
                scope="competitor_public",
            )
        return QueryPolicyDecision(allowed=True, scope="general")
