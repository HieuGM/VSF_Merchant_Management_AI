"""Unit tests for Merchant Profile and Evidence Repositories (Task 1).

Ensures:
- 8-dimension profile lookup works.
- `overall_score` is strictly stripped per security rule C2.
- Evidence references are properly fetched by ID prefix.
"""
from __future__ import annotations

from datetime import datetime
import pytest
from database.models import Merchant, MerchantProfile, Review, OperationalMetric
from repositories.merchant_profile_repository import MerchantProfileRepository
from repositories.evidence_repository import EvidenceRepository


@pytest.fixture
def sample_merchant_data(db_session):
    """Seed test merchant data in test DB session."""
    merchant = Merchant(
        merchant_id="test_merchant_001",
        name="Quán Cơm Tấm Sài Gòn",
        cuisine="Món Việt",
        city="TP. HCM",
        city_slug="tp-hcm",
        address="123 Nguyễn Trãi, Q1",
        lat=10.77,
        lng=106.69,
    )
    db_session.add(merchant)

    profile_json = {
        "merchant_id": "test_merchant_001",
        "tier": "gold",
        "overall_score": 0.85,  # Internal only — MUST be stripped
        "dimensions": {
            "food_quality": {
                "score": 8.5,
                "basis": "Đánh giá vị ngon từ 20 khách hàng",
                "evidence": [
                    {
                        "evidence_id": "ev_001",
                        "type": "positive_review",
                        "value": 4.5,
                        "ref_type": "review",
                        "ref_ids": ["REV-101"],
                        "source_kind": "real",
                    }
                ],
            },
            "image_quality": {"score": 7.0, "basis": "Ảnh HD nét", "evidence": []},
            "delivery_quality": {"score": 9.0, "basis": "Giao nhanh", "evidence": []},
            "packaging": {"score": 8.0, "basis": "Hộp đẹp", "evidence": []},
            "service": {"score": 8.5, "basis": "Phục vụ chu đáo", "evidence": []},
            "waiting_time": {"score": 7.5, "basis": "Chờ 12 phút", "evidence": []},
            "menu_diversity": {"score": 8.0, "basis": "30 món", "evidence": []},
            "price_level": {"score": 7.0, "basis": "Giá bình dân", "evidence": []},
        },
        "attributes": {"trending_dishes": ["Cơm tấm sườn bì chả"]},
    }

    profile = MerchantProfile(
        merchant_id="test_merchant_001",
        dimensions_json=profile_json["dimensions"],
        profile_json=profile_json,
        schema_version="1.0",
        source_kind="development_fixture",
    )
    db_session.add(profile)

    review = Review(
        review_id="REV-101",
        merchant_id="test_merchant_001",
        rating=4.5,
        text="Cơm tấm rất ngon, sườn mềm đậm đà!",
        sentiment="positive",
        created_at=datetime.utcnow(),
    )
    db_session.add(review)

    metric = OperationalMetric(
        merchant_id="test_merchant_001",
        avg_prep_time_min=12.5,
    )
    db_session.add(metric)

    db_session.flush()
    return merchant


def test_get_profile_returns_valid_schema(db_session, sample_merchant_data):
    repo = MerchantProfileRepository(db_session)
    profile = repo.get_profile("test_merchant_001")

    assert profile is not None
    assert profile["merchant_id"] == "test_merchant_001"
    assert "dimensions" in profile
    assert len(profile["dimensions"]) == 8


def test_get_profile_strips_overall_score_security_c2(db_session, sample_merchant_data):
    repo = MerchantProfileRepository(db_session)
    profile = repo.get_profile("test_merchant_001")

    assert profile is not None
    # C2 Rule: overall_score must NOT be in top-level or dimensions
    assert "overall_score" not in profile
    assert "overall_score" not in profile["dimensions"]


def test_get_profile_not_found(db_session):
    repo = MerchantProfileRepository(db_session)
    profile = repo.get_profile("non_existent_merchant")
    assert profile is None


def test_get_evidence_by_refs(db_session, sample_merchant_data):
    repo = EvidenceRepository(db_session)
    evidences = repo.get_evidence_by_refs(["REV-101", "METRIC-test_merchant_001"])

    assert len(evidences) == 2
    ref_map = {e["ref"]: e for e in evidences}

    assert "REV-101" in ref_map
    assert ref_map["REV-101"]["type"] == "review"
    assert "Cơm tấm rất ngon" in ref_map["REV-101"]["content"]

    assert "METRIC-test_merchant_001" in ref_map
    assert ref_map["METRIC-test_merchant_001"]["type"] == "operational_metric"
    assert ref_map["METRIC-test_merchant_001"]["avg_prep_time_min"] == 12.5
