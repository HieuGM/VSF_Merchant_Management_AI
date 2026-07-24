"""get_merchant_profile / get_trending_dishes read from the real DB (Bug-1 fix).

Requires Postgres (skips when unreachable). Proves the shared read-only tools resolve an
arbitrary seeded merchant from `merchant_profiles`, not just the bundled dev fixture.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core.errors import NotFoundError
from database.connection import SessionLocal, engine
from database.models import MerchantProfile
from tools.shared.shared_readonly_tools import get_merchant_profile, get_trending_dishes


def _require_db():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
    except OperationalError:
        pytest.skip("Postgres not reachable — integration test skipped.")


def _a_seeded_merchant_id() -> str:
    db = SessionLocal()
    try:
        row = db.query(MerchantProfile).first()
        if row is None:
            pytest.skip("merchant_profiles empty — seed required.")
        return row.merchant_id
    finally:
        db.close()


def test_get_merchant_profile_from_db():
    _require_db()
    mid = _a_seeded_merchant_id()
    profile = get_merchant_profile(mid)
    # 8-dimension contract present, internal aggregate stripped.
    assert "overall_score" not in profile
    assert "dimensions" in profile
    assert set(profile["dimensions"].keys()) >= {"food_quality", "price_level"}


def test_get_trending_dishes_from_db():
    _require_db()
    mid = _a_seeded_merchant_id()
    out = get_trending_dishes(mid)
    assert out["merchant_id"] == mid
    assert isinstance(out["trending_dishes"], list)


def test_unknown_merchant_raises_not_found():
    _require_db()
    with pytest.raises(NotFoundError):
        get_merchant_profile("definitely_not_a_real_merchant_id_xyz")
