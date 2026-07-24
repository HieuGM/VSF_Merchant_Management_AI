"""Preference delta reasoning — pure, rule-based, proposal-only (Phase 07)."""
from __future__ import annotations

from models.preference import UserProfilePublic
from services.preference_service import propose_deltas


def test_no_signal_returns_empty():
    prof = UserProfilePublic(user_id="u", budget_level="standard", distance_preference_km=3.0)
    assert propose_deltas(constraints={}, weather=None, profile=prof) == []


def test_rain_suggests_shorter_distance():
    prof = UserProfilePublic(user_id="u", distance_preference_km=5.0)
    out = propose_deltas(constraints={}, weather={"is_rain": True}, profile=prof)
    fields = {s.field for s in out}
    assert "distance_preference_km" in fields
    dist = next(s for s in out if s.field == "distance_preference_km")
    assert dist.value < 5.0 and dist.rationale


def test_budget_keyword_suggests_student():
    out = propose_deltas(constraints={"note": "mình là sinh viên"}, weather=None, profile=None)
    assert any(s.field == "budget_level" and s.value == "student" for s in out)


def test_every_suggestion_has_rationale_and_id():
    out = propose_deltas(
        constraints={"cuisine": "chay", "budget": "student"},
        weather={"is_rain": True},
        profile=UserProfilePublic(user_id="u", distance_preference_km=5.0),
    )
    assert out
    for s in out:
        assert s.delta_id and s.rationale and s.confidence >= 0
