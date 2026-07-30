"""DB-backed customer context tools (Phase 07 tests 4, 5).

Requires Postgres (skips when unreachable — A-04). Seeds `user_demo` idempotently."""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core.errors import NotFoundError
from database.connection import SessionLocal, engine
from database.models import PreferenceEvent, UserProfile
from scripts.seed_user_demo import DEMO_USER_ID, seed_user_demo
from tools.customer.customer_context_tools import get_user_profile, propose_profile_delta


def _require_db():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
    except OperationalError:
        pytest.skip("Postgres not reachable — integration test skipped.")


@pytest.fixture(scope="module", autouse=True)
def _seed():
    _require_db()
    seed_user_demo()


def test_get_user_profile_returns_seeded_profile():
    profile = get_user_profile(user_id=DEMO_USER_ID)
    assert profile["user_id"] == DEMO_USER_ID
    assert isinstance(profile["liked_cuisines"], list)


def test_get_user_profile_unknown_raises_not_found():
    with pytest.raises(NotFoundError):
        get_user_profile(user_id="user_that_does_not_exist")


def test_propose_profile_delta_does_not_persist():
    """Propose-only invariant (phase-04 F5 / audit canary extension).

    phase-04 introduces the FIRST write path to user_profiles (confirm). This canary now
    also snapshots user_profiles.{liked_cuisines,dietary,budget_level,distance_preference_km}
    before/after propose_profile_delta and asserts byte-identical — so a future leak of write
    logic into the propose path is caught here, not in production."""
    db = SessionLocal()
    try:
        evt_before = db.query(PreferenceEvent).count()
        row = db.get(UserProfile, DEMO_USER_ID)
        profile_before = None
        if row is not None:
            profile_before = {
                "liked_cuisines": list(row.liked_cuisines or []),
                "dietary": list(row.dietary or []),
                "budget_level": row.budget_level,
                "distance_preference_km": row.distance_preference_km,
            }
    finally:
        db.close()

    out = propose_profile_delta(
        user_id=DEMO_USER_ID,
        constraints={"cuisine": "chay", "note": "sinh viên"},
        weather={"is_rain": True},
    )
    assert out["count"] >= 1  # produced suggestions

    db = SessionLocal()
    try:
        evt_after = db.query(PreferenceEvent).count()
        row = db.get(UserProfile, DEMO_USER_ID)
        profile_after = None
        if row is not None:
            profile_after = {
                "liked_cuisines": list(row.liked_cuisines or []),
                "dietary": list(row.dietary or []),
                "budget_level": row.budget_level,
                "distance_preference_km": row.distance_preference_km,
            }
    finally:
        db.close()

    assert evt_before == evt_after, "propose_profile_delta must NOT write preference_events"
    assert profile_before == profile_after, (
        "propose_profile_delta must NOT mutate user_profiles (propose-only invariant)")
