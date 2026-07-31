"""Unit tests for public merchant search."""
from __future__ import annotations

from database.models import Merchant, MenuItem
from providers.cache.memory_adapter import InMemoryCache
from relational_test_fixtures import seed_relational_profile
from tools.merchant.search_tool import search_merchants


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


def test_search_merchants_relaxes_a_multiword_natural_language_keyword(
    db_session,
):
    target = Merchant(
        merchant_id="m_search_keyword_relax",
        name="Mr Chay Hà Nội",
        cuisine="Món Việt",
        city="Hà Nội",
        city_slug="ha_noi",
        address="12 Bà Triệu",
        diet_tags=["chay"],
        is_active=True,
    )
    db_session.add(target)
    seed_relational_profile(db_session, target.merchant_id, scores={})
    db_session.commit()

    result = search_merchants(
        query="quán chay",
        diet="chay",
        city="Hà Nội",
        db=db_session,
    )

    assert target.merchant_id in {merchant["merchant_id"] for merchant in result["merchants"]}


def test_search_merchants_cache_key_includes_all_result_affecting_filters(
    db_session,
):
    target = Merchant(
        merchant_id="m_search_cache_filter",
        name="Bếp Chay Cache",
        cuisine="Món Việt",
        city="Hà Nội",
        city_slug="ha_noi",
        address="12 Bà Triệu",
        diet_tags=["chay"],
        is_active=True,
    )
    db_session.add(target)
    seed_relational_profile(db_session, target.merchant_id, scores={})
    db_session.commit()

    cache = InMemoryCache()
    chay_result = search_merchants(
        query="quán chay",
        diet="chay",
        city="ha_noi",
        db=db_session,
        cache=cache,
    )
    keto_result = search_merchants(
        query="quán chay",
        diet="keto",
        city="ha_noi",
        db=db_session,
        cache=cache,
    )

    assert target.merchant_id in {
        merchant["merchant_id"] for merchant in chay_result["merchants"]
    }
    assert target.merchant_id not in {
        merchant["merchant_id"] for merchant in keto_result["merchants"]
    }


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


def test_search_merchants_expands_h3_resolution_and_ranks_exact_distance(db_session):
    anchor = Merchant(
        merchant_id="h3-search-anchor",
        name="H3 Search Anchor",
        cuisine="H3 Candidate Cuisine",
        city="Đà Nẵng",
        city_slug="da_nang",
        lat=16.0544,
        lng=108.2022,
        is_active=True,
    )
    nearby = Merchant(
        merchant_id="h3-search-nearby",
        name="H3 Search Nearby",
        cuisine="H3 Candidate Cuisine",
        city="Đà Nẵng",
        city_slug="da_nang",
        lat=16.055,
        lng=108.203,
        is_active=True,
    )
    expanded = Merchant(
        merchant_id="h3-search-expanded",
        name="H3 Search Expanded",
        cuisine="H3 Candidate Cuisine",
        city="Đà Nẵng",
        city_slug="da_nang",
        lat=16.105,
        lng=108.2022,
        is_active=True,
    )
    db_session.add_all([anchor, nearby, expanded])
    db_session.commit()

    nearby_result = search_merchants(
        cuisine="H3 Candidate Cuisine",
        anchor_merchant_id=anchor.merchant_id,
        radius_km=2.0,
        sort_by="distance",
        db=db_session,
    )

    assert nearby_result["h3_resolution"] == 9
    assert nearby_result["expanded_search"] is False
    assert nearby_result["merchants"][0]["merchant_id"] == nearby.merchant_id
    assert nearby_result["merchants"][0]["distance_km"] is not None

    db_session.delete(nearby)
    db_session.commit()

    expanded_result = search_merchants(
        cuisine="H3 Candidate Cuisine",
        anchor_merchant_id=anchor.merchant_id,
        radius_km=2.0,
        sort_by="distance",
        db=db_session,
    )

    assert expanded_result["h3_resolution"] == 6
    assert expanded_result["expanded_search"] is True
    assert expanded_result["effective_radius_km"] == 8.0
    assert [item["merchant_id"] for item in expanded_result["merchants"]] == [
        expanded.merchant_id
    ]


def test_search_merchants_requires_all_meaningful_dish_terms(db_session):
    target = Merchant(
        merchant_id="dish-phrase-target",
        name="Diệu - Bún Chả Cá Sứa",
        cuisine="Món Việt",
        city="TP. HCM",
        city_slug="tp_hcm",
        ingredient_tags=["cá"],
        is_active=True,
    )
    unrelated = Merchant(
        merchant_id="dish-phrase-unrelated",
        name="Bánh Mì Hà Nội",
        cuisine="Món Việt",
        city="TP. HCM",
        city_slug="tp_hcm",
        ingredient_tags=["cá"],
        is_active=True,
    )
    db_session.add_all([target, unrelated])
    db_session.commit()

    result = search_merchants(query="bún cá", city="tp_hcm", db=db_session)

    ids = {merchant["merchant_id"] for merchant in result["merchants"]}
    assert target.merchant_id in ids
    assert unrelated.merchant_id not in ids


def test_search_merchants_reports_final_h3_expansion_when_no_match(db_session):
    anchor = Merchant(
        merchant_id="h3-empty-anchor",
        name="H3 Empty Anchor",
        cuisine="Anchor Only",
        city="Đà Nẵng",
        city_slug="da_nang",
        lat=16.0544,
        lng=108.2022,
        is_active=True,
    )
    db_session.add(anchor)
    db_session.commit()

    result = search_merchants(
        cuisine="Cuisine That Does Not Exist",
        anchor_merchant_id=anchor.merchant_id,
        radius_km=2.0,
        db=db_session,
    )

    assert result["count"] == 0
    assert result["h3_resolution"] == 6
    assert result["effective_radius_km"] == 8.0
    assert result["expanded_search"] is True
