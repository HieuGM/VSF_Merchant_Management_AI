"""Unit tests for the unified active-constraints layer (loader + enforcer + catalog).

Replaces the per-case tests removed with the scattered filters (_detect_dietary_conflict,
_declared_persistent_preference, _recalled_dietary_filter). Covers the user's exact bug:
"không ăn được hải sản" → "xin chào" must NOT suggest sushi (allergy enforced PROACTIVELY on
every turn, not just when the query requests the allergen). Plus chay, partial-overlap, and the
confirm-gate. Pure functions, no DB."""
from __future__ import annotations

from types import SimpleNamespace as NS

from services.active_constraints_enforcer import (
    apply_constraints,
    hard_filter_l1,
    query_requests_restriction,
    violates_hard,
)
from services.active_constraints_loader import build_active_constraints as build


def U(t): return {"sender": "user", "text": t}
def A(t): return {"sender": "agent", "text": t}
def M(name, cuisine, tags=None, dishes=None):
    return {"name": name, "cuisine": cuisine, "taste_tags": tags or [], "top_dishes": dishes or []}


# --- LOADER: derives constraints from all 3 memory layers ---
def test_seafood_allergy_from_note_is_hard():
    cs = build(NS(dietary=[], disliked_cuisines=[], context_memory={"notes": ["Tôi không ăn được hải sản"]}), [], "xin chào")
    assert [(c.type, c.scope, c.enforce, c.persistence) for c in cs.hard] == [("allergy", "seafood", "hard_filter", "durable")]


def test_chay_durable_from_profile_dietary():
    cs = build(NS(dietary=["chay"], disliked_cuisines=[], context_memory={}), [], "tìm quán")
    assert any(c.scope == "chay" and c.persistence == "durable" for c in cs.hard)


def test_chay_session_recall_transient():
    # "nay ăn chay" (no durable marker) → session-scoped, recalled on a LATER turn.
    cs = build(None, [U("nay tôi ăn chay")], "tìm phở")
    assert any(c.scope == "chay" and c.persistence == "session" for c in cs.hard)


def test_diet_break_contradiction_suppresses_chay():
    cs = build(None, [U("từ giờ ăn chay")], "hôm nay phá lệ ăn thịt nha")
    assert all(c.scope != "chay" for c in cs.hard)


def test_disliked_cuisines_are_soft_not_hard():
    cs = build(NS(dietary=[], disliked_cuisines=["Đồ cay"], context_memory={}), [], "ăn gì")
    assert any(c.type == "dislike" and c.enforce == "soft_penalty" for c in cs.soft)
    assert not cs.hard


def test_agent_turn_allergy_does_not_count():
    # Only USER declarations register; an agent mentioning the food is not a restriction.
    cs = build(None, [A("mình gợi ý quán hải sản")], "tìm phở")
    assert cs.is_empty


def test_empty_when_no_declaration():
    assert build(None, [U("chào bạn")], "tìm phở").is_empty


def test_same_turn_declaration_in_current_query():
    # TC-48: 'từ giờ ăn chay trường' is the CURRENT message (not yet in prior_turns) → still a
    # hard chay constraint so a same-turn search filters results.
    cs = build(None, [], "Từ giờ nhớ tôi ăn chay trường nhé")
    assert any(c.scope == "chay" for c in cs.hard)


# --- ENFORCER: the user's bug + partial-overlap + chay + confirm-gate ---
def test_sushi_on_hello_dropped_allergy_proactive():
    # THE bug: seafood allergy + generic 'xin chào' query → sushi place dropped, phở kept.
    cs = build(NS(dietary=[], disliked_cuisines=[], context_memory={"notes": ["dị ứng hải sản"]}), [], "xin chào")
    results = [M("Sushi Yuki", "Nhật/Sushi", dishes=[{"name": "sashimi"}]), M("Phở Bò", "Việt")]
    assert [r["name"] for r in apply_constraints(results, cs)] == ["Phở Bò"]


def test_mixed_restaurant_with_safe_dish_kept_partial_overlap():
    cs = build(NS(dietary=[], disliked_cuisines=[], context_memory={"notes": ["dị ứng hải sản"]}), [], "ăn gì")
    mixed = M("Quán Việt", "Việt", dishes=[{"name": "phở bò"}, {"name": "tôm nướng"}])  # has a safe dish
    assert apply_constraints([mixed], cs) == [mixed]


def test_chay_want_drops_non_chay():
    cs = build(NS(dietary=["chay"], disliked_cuisines=[], context_memory={}), [], "tìm quán")
    results = [M("Phở Bò", "Việt", dishes=[{"name": "phở bò"}]), M("An Lạc", "Chay", ["chay"], [{"name": "phở chay"}])]
    assert [r["name"] for r in apply_constraints(results, cs)] == ["An Lạc"]


def test_confirm_gate_when_query_requests_allergen():
    cs = build(NS(dietary=[], disliked_cuisines=[], context_memory={"notes": ["dị ứng hải sản"]}), [], "tìm hải sản")
    ans = query_requests_restriction("tìm quán hải sản", cs)
    assert ans is not None and "hải sản" in ans
    # Generic query → no confirm (filter handles it silently).
    assert query_requests_restriction("xin chào", cs) is None


def test_confirm_gate_not_fired_on_declaration():
    # DECLARING the allergy ("tôi dị ứng/không ăn được hải sản") is NOT a request → no confirm
    # (the live-test regression: it used to false-fire on the declaration turn itself).
    cs = build(NS(dietary=[], disliked_cuisines=[], context_memory={"notes": ["dị ứng hải sản"]}), [], "")
    assert query_requests_restriction("Tôi không ăn được hải sản, bị dị ứng", cs) is None
    assert query_requests_restriction("mình dị ứng hải sản nhé", cs) is None


def test_no_constraints_keeps_all():
    cs = build(None, [], "tìm phở")
    results = [M("Sushi", "Nhật"), M("Phở", "Việt")]
    assert len(apply_constraints(results, cs)) == 2


# --- L1 (ORM-style, no dishes): hard_filter_l1 used by should_hard_filter ---
def test_hard_filter_l1_drops_seafood_cuisine():
    cs = build(NS(dietary=[], disliked_cuisines=[], context_memory={"notes": ["dị ứng hải sản"]}), [], "ăn gì")
    sushi = NS(cuisine="Nhật/Sushi", name="Sushi Y", taste_tags=[])
    pho = NS(cuisine="Việt", name="Phở", taste_tags=[])
    assert hard_filter_l1(sushi, cs) is not None
    assert hard_filter_l1(pho, cs) is None


# --- integration: _pre_search_guard uses the unified confirm-gate ---
def test_pre_search_guard_confirm_via_constraints():
    from flows.customer_flow import _pre_search_guard as guard

    prior = [U("Tôi không ăn được hải sản"), A("đã ghi nhận")]
    out = guard("Tìm quán hải sản", prior, None, False)
    assert out is not None and out[1] == "dietary_conflict" and "hải sản" in out[0]
    # Generic query on the same allergy → NOT a confirm (proactive filter handles it downstream).
    assert guard("xin chào", prior, None, False) is None
