"""Unit tests for the phase-03 weather helpers in flows.customer_flow.

These are pure dict→string transforms (no LLM, no DB): _weather_summary tolerates
missing keys / synthesizes from flags, _format_weather_hint wraps it for the prompt,
and _merge_weather_suggestions short-circuits to a no-op without an override. Guards
the truth-first behavior (never fabricate a weather condition the client did not supply)."""
from __future__ import annotations

from flows.customer_flow import (
    _format_weather_hint,
    _merge_weather_suggestions,
    _weather_summary,
)


# --- _weather_summary: tolerate missing keys, synthesize from flags ---
def test_weather_summary_none_and_empty():
    assert _weather_summary(None) is None
    assert _weather_summary({}) is None              # nothing usable
    # Flags present but all False → no condition to assert → None.
    assert _weather_summary({"is_rain": False, "is_cold": False, "is_hot": False}) is None


def test_weather_summary_prefers_explicit_summary():
    # A client-supplied summary string wins verbatim over flag synthesis.
    assert _weather_summary({"summary": "Mưa rào rào rào"}) == "Mưa rào rào rào"


def test_weather_summary_synthesizes_from_flags():
    assert _weather_summary({"is_rain": True}) == "trời mưa"
    assert _weather_summary({"is_cold": True}) == "trời lạnh"
    assert _weather_summary({"is_hot": True}) == "trời nóng"
    # Rain stacks with a temperature flag; cold/hot are exclusive (elif), never both.
    assert _weather_summary({"is_rain": True, "is_cold": True}) == "trời mưa, trời lạnh"
    assert _weather_summary({"is_rain": True, "is_hot": True}) == "trời mưa, trời nóng"
    # is_cold takes precedence over is_hot when both are set (elif ordering).
    assert _weather_summary({"is_cold": True, "is_hot": True}) == "trời lạnh"


# --- _format_weather_hint: empty when nothing usable, else the instruction line ---
def test_format_weather_hint_empty_cases():
    assert _format_weather_hint(None) == ""
    assert _format_weather_hint({}) == ""            # nothing usable → no hint


def test_format_weather_hint_emits_instruction():
    out = _format_weather_hint({"summary": "Trời mưa to"})
    assert "THỜI TIẾT" in out
    assert "Trời mưa to" in out
    # Tells the preference agent to USE this instead of calling the weather tool (no double-fetch).
    assert "DÙNG THAY" in out


# --- _merge_weather_suggestions: no-override short-circuit ---
def test_merge_weather_suggestions_noop_without_override():
    """No weather_override → existing suggestions returned unchanged (no propose_deltas call,
    no import side-effect). Guards the B3 short-circuit is a pure no-op when idle."""
    existing = [{"field": "liked_cuisines", "operation": "boost", "value": "Việt"}]
    out = _merge_weather_suggestions(existing, None, {}, None)
    assert out is existing


# --- _merge_weather_suggestions: rain override fires + dedupes (B3 deep) ---
# propose_deltas(rain, profile.distance_preference_km=5.0) yields exactly ONE delta:
#   (distance_preference_km, "set", 3.0)   [min(5.0, 3.0)].
# The merge must append it when absent and DEDUPE (by field+operation+value) when present.
def _profile(distance_km: float = 5.0):
    from types import SimpleNamespace
    return SimpleNamespace(
        distance_preference_km=distance_km, budget_level=None,
        liked_cuisines=[], dietary=[],
    )


def test_merge_weather_suggestions_appends_rain_delta():
    # Empty crew suggestions + rain → the rain (prefer-nearby) delta is injected server-side.
    merged = _merge_weather_suggestions([], {"is_rain": True}, {}, _profile(5.0))
    fields = [m.get("field") for m in merged]
    assert "distance_preference_km" in fields
    dist = next(m for m in merged if m.get("field") == "distance_preference_km")
    assert dist["value"] == 3.0 and dist["operation"] == "set"


def test_merge_weather_suggestions_preserves_existing_and_dedupes():
    # A non-overlapping existing delta survives alongside the rain delta.
    existing = [{"field": "liked_cuisines", "operation": "add", "value": "Việt"}]
    merged = _merge_weather_suggestions(existing, {"is_rain": True}, {}, _profile(5.0))
    fields = {m.get("field") for m in merged}
    assert fields == {"liked_cuisines", "distance_preference_km"}
    # The exact delta the rain produces, already present → DEDUPED (no second copy).
    dup_existing = [{"field": "distance_preference_km", "operation": "set", "value": 3.0}]
    merged2 = _merge_weather_suggestions(dup_existing, {"is_rain": True}, {}, _profile(5.0))
    assert len([m for m in merged2 if m.get("field") == "distance_preference_km"]) == 1


def test_merge_weather_suggestions_no_delta_when_already_nearby():
    # Profile already within 3 km → propose_deltas rain rule is a no-op (target==current),
    # so the merge returns existing unchanged (no spurious shrink suggestion).
    existing = [{"field": "liked_cuisines", "operation": "add", "value": "Việt"}]
    merged = _merge_weather_suggestions(existing, {"is_rain": True}, {}, _profile(2.0))
    assert merged == existing
