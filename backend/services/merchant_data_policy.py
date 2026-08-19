"""Code-enforced owner-private and competitor-public data policy."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.errors import ForbiddenError

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
