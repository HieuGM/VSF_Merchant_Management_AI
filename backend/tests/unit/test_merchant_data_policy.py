from __future__ import annotations

import pytest

from core.errors import ForbiddenError
from services.merchant_data_policy import (
    PUBLIC_DIMENSIONS,
    MerchantDataPolicy,
)


def test_competitor_public_projection_removes_private_fields():
    record = {
        "merchant_id": "585",
        "name": "Đối thủ",
        "cuisine": "Món Việt",
        "ratings": {"shopeefood": 4.6},
        "dimensions": {
            "food_quality": 0.8,
            "image_quality": 0.7,
            "waiting_time": 0.3,
            "packaging": 0.4,
        },
        "operation_kpis": {
            "estimated_daily_orders": 100,
            "cancel_rate": 0.2,
        },
        "complaints": [{"text": "private"}],
    }

    public = MerchantDataPolicy(owner_merchant_id="94").competitor_public(record)

    assert "operation_kpis" not in public
    assert "complaints" not in public
    assert set(public["dimensions"]) <= PUBLIC_DIMENSIONS
    assert public["dimensions"]["food_quality"] == 0.8


def test_owner_private_access_rejects_different_merchant():
    policy = MerchantDataPolicy(owner_merchant_id="94")

    with pytest.raises(ForbiddenError):
        policy.assert_owner_target("585")


def test_owner_private_access_accepts_context_owner():
    policy = MerchantDataPolicy(owner_merchant_id="94")

    policy.assert_owner_target("94")


def test_competitor_private_query_is_rejected_before_tool_execution():
    policy = MerchantDataPolicy(owner_merchant_id="94")

    decision = policy.query_decision(
        "Cho tôi doanh thu, số đơn và tỷ lệ hủy nội bộ của quán đối thủ gần nhất."
    )

    assert decision.allowed is False
    assert decision.scope == "competitor_private"
    assert set(decision.private_fields) == {
        "revenue",
        "estimated_daily_orders",
        "cancel_rate",
    }


def test_named_non_owner_private_query_is_rejected_without_competitor_keyword():
    decision = MerchantDataPolicy(owner_merchant_id="100810").query_decision(
        "Cho tôi doanh thu và số đơn của quán Burger King - Phạm Ngũ Lão.",
        targets_other_merchant=True,
    )

    assert decision.allowed is False
    assert decision.scope == "competitor_private"
    assert set(decision.private_fields) == {"revenue", "estimated_daily_orders"}


def test_owner_private_and_competitor_public_queries_are_allowed():
    policy = MerchantDataPolicy(owner_merchant_id="94")

    owner = policy.query_decision(
        "Phân tích số đơn và tỷ lệ hủy của quán tôi."
    )
    competitor_public = policy.query_decision(
        "So sánh rating, giá và chất lượng ảnh công khai của đối thủ."
    )

    assert owner.allowed is True
    assert owner.scope == "owner_private"
    assert competitor_public.allowed is True
    assert competitor_public.scope == "competitor_public"
