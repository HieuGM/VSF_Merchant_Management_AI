"""Unit tests for Profile Summary and Operational Metrics tools."""
from __future__ import annotations

from database.models import Merchant, OperationalMetric
from relational_test_fixtures import seed_relational_profile
from tools.merchant.profile_tool import (
    get_merchant_profile_summary,
    GetMerchantProfileSummaryTool,
)
from tools.merchant.metrics_tool import (
    get_merchant_operational_metrics,
    GetMerchantOperationalMetricsTool,
)


def test_get_merchant_profile_summary_dimension_filtering(db_session):
    m = Merchant(
        merchant_id="m_profile_summary_01",
        name="Quán Bún Cả Hà Nội",
        cuisine="Món Việt",
        city="Hà Nội",
        city_slug="ha-noi",
    )
    db_session.add(m)
    seed_relational_profile(
        db_session,
        "m_profile_summary_01",
        scores={"waiting_time": 0.42, "food_quality": 0.85},
    )
    db_session.commit()

    # Fetch only specific dimension
    res = get_merchant_profile_summary(
        merchant_id="m_profile_summary_01",
        dimensions=["waiting_time"],
        db=db_session,
    )
    assert res["status"] == "ok"
    assert res["merchant_id"] == "m_profile_summary_01"
    assert "dimensions" in res
    assert "waiting_time" in res["dimensions"]
    assert "food_quality" not in res["dimensions"]
    # Security Rule C2 check
    assert "overall_score" not in res
    assert "overall_score_internal" not in res


def test_get_merchant_profile_summary_tool_class(db_session, monkeypatch):
    m = Merchant(
        merchant_id="m_profile_tool_class_01",
        name="Quán Phở Thìn",
        cuisine="Món Phở",
        city="Hà Nội",
        city_slug="ha-noi",
    )
    db_session.add(m)
    seed_relational_profile(db_session, "m_profile_tool_class_01", scores={"food_quality": 0.80})
    db_session.commit()

    import tools.merchant.profile_tool as profile_tool_mod
    monkeypatch.setattr(profile_tool_mod, "SessionLocal", lambda: db_session)

    tool = GetMerchantProfileSummaryTool()
    output_str = tool._run(merchant_id="m_profile_tool_class_01", dimensions=["food_quality"])
    assert "m_profile_tool_class_01" in output_str
    assert "food_quality" in output_str
    assert "overall_score" not in output_str


def test_get_merchant_operational_metrics(db_session):
    m = Merchant(
        merchant_id="m_metrics_01",
        name="Quán Test Metrics",
        cuisine="Món Việt",
        city="Hà Nội",
        city_slug="ha-noi",
    )
    db_session.add(m)
    db_session.flush()
    metric = OperationalMetric(
        merchant_id="m_metrics_01",
        avg_prep_time_min=18.5,
        on_time_rate=0.92,
        cancel_rate=0.03,
        acceptance_rate=0.98,
        source_kind="development_fixture",
    )
    db_session.add(metric)
    db_session.commit()

    res = get_merchant_operational_metrics("m_metrics_01", db=db_session)
    assert res["status"] == "ok"
    assert res["metrics"]["avg_prep_time_min"] == 18.5
    assert res["metrics"]["on_time_rate"] == 0.92


def test_get_merchant_operational_metrics_tool_class(db_session, monkeypatch):
    m = Merchant(
        merchant_id="m_metrics_tool_01",
        name="Quán Test Tool",
        cuisine="Món Việt",
        city="Hà Nội",
        city_slug="ha-noi",
    )
    db_session.add(m)
    db_session.flush()
    metric = OperationalMetric(
        merchant_id="m_metrics_tool_01",
        avg_prep_time_min=22.0,
        on_time_rate=0.85,
        source_kind="development_fixture",
    )
    db_session.add(metric)
    db_session.commit()

    import tools.merchant.metrics_tool as metrics_tool_mod
    monkeypatch.setattr(metrics_tool_mod, "SessionLocal", lambda: db_session)

    tool = GetMerchantOperationalMetricsTool()
    output_str = tool._run(merchant_id="m_metrics_tool_01")
    assert "m_metrics_tool_01" in output_str
    assert "22.0" in output_str
