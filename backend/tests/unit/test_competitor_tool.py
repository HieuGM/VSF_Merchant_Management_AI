"""Unit tests for Competitor Benchmark Tool (Task 4)."""
from __future__ import annotations

from database.models import Merchant, MerchantProfile
from relational_test_fixtures import seed_relational_profile
from tools.merchant.competitor_tool import compare_merchant_benchmark, CompareMerchantBenchmarkTool


def _make_merchant(session, mid: str, lat: float, lng: float, cuisine: str = "Cơm Niêu Test") -> Merchant:
    m = Merchant(
        merchant_id=mid,
        name=f"Quán {mid}",
        cuisine=cuisine,
        city="Hà Nội",
        city_slug="ha-noi",
        lat=lat,
        lng=lng,
        is_active=True,
    )
    session.add(m)
    session.flush()
    return m


def test_compare_merchant_benchmark_finds_nearby_competitors(db_session):
    # Target at (21.028, 105.854)
    _make_merchant(db_session, "m_bench_target", lat=21.028, lng=105.854)
    seed_relational_profile(db_session, "m_bench_target", scores={"food_quality": 0.70, "service": 0.65})

    # Competitor ~0.3 km away (same cuisine)
    _make_merchant(db_session, "m_bench_comp_01", lat=21.030, lng=105.856)
    seed_relational_profile(db_session, "m_bench_comp_01", scores={"food_quality": 0.85, "service": 0.80})

    # Competitor 15 km away (should be excluded at 5 km radius)
    _make_merchant(db_session, "m_bench_comp_far", lat=21.16, lng=105.85)
    seed_relational_profile(db_session, "m_bench_comp_far", scores={"food_quality": 0.90})

    db_session.commit()

    res = compare_merchant_benchmark("m_bench_target", radius_km=5.0, db=db_session)
    assert res["status"] == "ok"
    assert res["target_merchant_id"] == "m_bench_target"
    assert "competitors" in res

    comp_ids = [c["merchant_id"] for c in res["competitors"]]
    assert "m_bench_comp_01" in comp_ids
    assert "m_bench_comp_far" not in comp_ids

    # Verify delta structure
    comp = next(c for c in res["competitors"] if c["merchant_id"] == "m_bench_comp_01")
    assert "delta_vs_target" in comp
    assert "food_quality" in comp["delta_vs_target"]
    # Competitor food_quality (0.85) > target (0.70), delta should be positive
    assert comp["delta_vs_target"]["food_quality"] > 0


def test_compare_merchant_benchmark_dimension_filter(db_session):
    _make_merchant(db_session, "m_bench_dim_target", lat=21.028, lng=105.854)
    seed_relational_profile(db_session, "m_bench_dim_target", scores={"food_quality": 0.70, "service": 0.65})

    _make_merchant(db_session, "m_bench_dim_comp", lat=21.030, lng=105.855)
    seed_relational_profile(db_session, "m_bench_dim_comp", scores={"food_quality": 0.80, "service": 0.75})
    db_session.commit()

    res = compare_merchant_benchmark(
        "m_bench_dim_target",
        dimensions=["food_quality"],
        radius_km=5.0,
        db=db_session,
    )
    assert res["status"] == "ok"
    assert res["dimensions_compared"] == ["food_quality"]
    assert "service" not in res["target_scores"]


def test_compare_merchant_benchmark_not_found(db_session):
    res = compare_merchant_benchmark("m_not_exist_999", db=db_session)
    assert res["status"] == "not_found"


def test_compare_merchant_benchmark_no_location(db_session):
    m = Merchant(
        merchant_id="m_no_loc_001",
        name="Quán Không Địa Chỉ",
        cuisine="Món Việt",
        city="Hà Nội",
        city_slug="ha-noi",
        # No lat/lng
    )
    db_session.add(m)
    db_session.commit()

    res = compare_merchant_benchmark("m_no_loc_001", db=db_session)
    assert res["status"] == "no_location"


def test_compare_merchant_benchmark_tool_class(db_session, monkeypatch):
    _make_merchant(db_session, "m_bench_tool_01", lat=21.028, lng=105.854)
    seed_relational_profile(db_session, "m_bench_tool_01", scores={"food_quality": 0.75})
    db_session.commit()

    import tools.merchant.competitor_tool as mod
    monkeypatch.setattr(mod, "SessionLocal", lambda: db_session)

    tool = CompareMerchantBenchmarkTool()
    output = tool._run(merchant_id="m_bench_tool_01", radius_km=5.0, limit=3)
    assert "m_bench_tool_01" in output
    assert "status" in output
