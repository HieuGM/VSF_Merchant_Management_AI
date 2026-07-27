"""Unit tests for Search & Discovery Tools (search_merchants, search_trending_dishes)."""
from __future__ import annotations

from database.models import Merchant, MarketTrendingDish, MenuItem
from relational_test_fixtures import seed_relational_profile
from tools.merchant.search_tool import (
    search_merchants,
    SearchMerchantsTool,
    search_trending_dishes,
    SearchTrendingDishesTool,
)


def test_search_merchants_with_filters_and_projection(db_session):
    m1 = Merchant(
        merchant_id="m_search_01",
        name="Phở Bò Hà Nội Độc Đáo",
        cuisine="Món Việt Phở Độc Đáo",
        city="Hà Nội",
        city_slug="ha-noi",
        address="12 Lê Lợi",
        lat=21.028,
        lng=105.854,
        is_active=True,
    )
    m2 = Merchant(
        merchant_id="m_search_02",
        name="Trà Sữa Gong Cha",
        cuisine="Trà sữa",
        city="Hà Nội",
        city_slug="ha-noi",
        address="88 Nguyễn Huệ",
        lat=21.030,
        lng=105.850,
        is_active=True,
    )
    db_session.add_all([m1, m2])
    seed_relational_profile(db_session, "m_search_01", scores={"food_quality": 0.88})
    seed_relational_profile(db_session, "m_search_02", scores={"food_quality": 0.70})
    db_session.commit()

    res = search_merchants(cuisine="Món Việt Phở Độc Đáo", city="Hà Nội", db=db_session)
    assert res["status"] == "ok"
    assert len(res["merchants"]) >= 1
    assert any(m["merchant_id"] == "m_search_01" for m in res["merchants"])
    item = next(m for m in res["merchants"] if m["merchant_id"] == "m_search_01")
    assert item["name"] == "Phở Bò Hà Nội Độc Đáo"
    assert item["price_level"] == "trung bình"
    assert "overall_score" not in item
    assert "overall_score_internal" not in item


def test_search_merchants_tool_class(db_session, monkeypatch):
    m = Merchant(
        merchant_id="m_search_tool_01",
        name="Đặc Sản Phở Hà Nội",
        cuisine="Món Phở Đặc Biệt",
        city="Hà Nội",
        city_slug="ha-noi",
        address="12 Lê Lợi",
    )
    db_session.add(m)
    seed_relational_profile(db_session, "m_search_tool_01", scores={"food_quality": 0.80})
    db_session.commit()

    import tools.merchant.search_tool as search_tool_mod
    monkeypatch.setattr(search_tool_mod, "SessionLocal", lambda: db_session)

    tool = SearchMerchantsTool()
    output_str = tool._run(cuisine="Món Phở Đặc Biệt")
    assert "m_search_tool_01" in output_str


def test_search_merchants_filters_numeric_menu_budget(db_session):
    cheap = Merchant(
        merchant_id="m_search_budget_cheap",
        name="Cơm Bình Dân Giá Tốt",
        cuisine="Cơm Ngân Sách Test",
        city="Đà Nẵng",
        city_slug="da_nang",
        address="1 Hải Châu",
        is_active=True,
    )
    expensive = Merchant(
        merchant_id="m_search_budget_expensive",
        name="Nhà Hàng Cao Cấp",
        cuisine="Cơm Ngân Sách Test",
        city="Đà Nẵng",
        city_slug="da_nang",
        address="2 Hải Châu",
        is_active=True,
    )
    db_session.add_all([cheap, expensive])
    seed_relational_profile(db_session, cheap.merchant_id, scores={})
    seed_relational_profile(db_session, expensive.merchant_id, scores={})
    db_session.add_all(
        [
            MenuItem(
                item_id="item_budget_cheap",
                merchant_id=cheap.merchant_id,
                name="Cơm gà",
                price=45_000,
                is_available=True,
            ),
            MenuItem(
                item_id="item_budget_expensive",
                merchant_id=expensive.merchant_id,
                name="Cơm đặc biệt",
                price=150_000,
                is_available=True,
            ),
        ]
    )
    db_session.commit()

    result = search_merchants(
        cuisine="Cơm Ngân Sách Test",
        city="Đà Nẵng",
        max_menu_price=50_000,
        db=db_session,
    )

    ids = {item["merchant_id"] for item in result["merchants"]}
    assert cheap.merchant_id in ids
    assert expensive.merchant_id not in ids
    cheap_result = next(
        item for item in result["merchants"] if item["merchant_id"] == cheap.merchant_id
    )
    assert cheap_result["menu_price_min"] == 45_000
    assert cheap_result["menu_price_median"] == 45_000


def test_search_trending_dishes(db_session):
    dish = MarketTrendingDish(
        city_slug="ha-noi",
        cuisine="Món Việt",
        dish_name="Phở Bò Tái Nạm",
        trend_score=0.92,
        rank=1,
    )
    db_session.add(dish)
    db_session.commit()

    res = search_trending_dishes(cuisine="Món Việt", city_slug="ha-noi", db=db_session)
    assert res["status"] == "ok"
    assert len(res["trending_dishes"]) >= 1
    assert any(d["dish_name"] == "Phở Bò Tái Nạm" for d in res["trending_dishes"])


def test_search_trending_dishes_tool_class(db_session, monkeypatch):
    dish = MarketTrendingDish(
        city_slug="ha-noi",
        cuisine="Món Việt Phở",
        dish_name="Phở Bò Tái Nạm Độc Đáo",
        trend_score=0.95,
        rank=1,
    )
    db_session.add(dish)
    db_session.commit()

    import tools.merchant.search_tool as search_tool_mod
    monkeypatch.setattr(search_tool_mod, "SessionLocal", lambda: db_session)

    tool = SearchTrendingDishesTool()
    output_str = tool._run(cuisine="Món Việt Phở", city_slug="ha-noi")
    assert "Phở Bò Tái Nạm Độc Đáo" in output_str
