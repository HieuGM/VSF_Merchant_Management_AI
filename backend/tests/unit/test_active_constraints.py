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


# --- COLLISION-SAFE MATCHER: homophones + substrings must not false-fire (audit group 1) ---
# Vietnamese folds tones away, merging crab≈của, mud-crab≈chair, clam≈sauce, vegetarian≈run.
# A bare substring matcher false-fired on all of these — dropping 'Cơm Của Mẹ' / 'Nhà hàng Ngọc'
# for a seafood-allergic user, or force-vegetarian-filtering a jogger. These prove the fix.
def test_cua_possessive_not_seafood_but_crab_is():
    assert all(c.scope != "seafood" for c in build(None, [U("tôi không ăn được cơm của mẹ")], "ăn gì").hard)
    assert any(c.scope == "seafood" for c in build(None, [U("tôi không ăn được cua")], "ăn gì").hard)


def test_sot_sauce_not_seafood():
    # 'sốt' (sauce) must not trip seafood; a sauce-named dish/merchant is not dropped.
    assert all(c.scope != "seafood" for c in build(None, [U("tôi không ăn được nước sốt")], "ăn gì").hard)
    cs = build(NS(dietary=[], disliked_cuisines=[], context_memory={"notes": ["dị ứng hải sản"]}), [], "ăn gì")
    assert violates_hard(M("Bún Sốt Cay", "Việt", dishes=[{"name": "bún sốt"}]), cs) is None


def test_ngoc_name_not_seafood():
    cs = build(NS(dietary=[], disliked_cuisines=[], context_memory={"notes": ["dị ứng hải sản"]}), [], "ăn gì")
    assert violates_hard(M("Nhà hàng Ngọc Su", "Ăn gia đình"), cs) is None  # 'ngọc' ⊃ 'oc' substring killed
    assert violates_hard(M("Sushi Yuki", "Nhật", dishes=[{"name": "sashimi"}]), cs) is not None  # real seafood still drops


def test_ghe_intensifier_not_seafood():
    assert all(c.scope != "seafood" for c in build(None, [U("đồ cay ghê, không ăn được")], "ăn gì").hard)


def test_chay_run_not_diet():
    # 'chạy bộ' (jogging) must NOT impose a vegetarian filter for the rest of the session.
    cs = build(None, [U("gợi ý quán gần nơi tôi hay chạy bộ")], "tìm phở")
    assert all(c.scope != "chay" for c in cs.hard)
    # but a real vegetarian declaration still registers
    assert any(c.scope == "chay" for c in build(None, [U("hôm nay tôi ăn chay")], "tìm phở").hard)


# --- MEMORY-RECALL GUARDS (audit group 2) ---
def test_question_not_diet_declaration():
    # ASKING 'có món chay không?' is not a vegetarian declaration.
    assert all(c.scope != "chay" for c in build(None, [], "quán này có món chay không?").hard)


def test_diet_negation_not_a_declaration():
    assert all(c.scope != "chay" for c in build(None, [], "tôi không ăn chay").hard)


def test_allergy_recovery_suppressed():
    prof = NS(dietary=[], disliked_cuisines=[], context_memory={"notes": ["tôi không còn dị ứng hải sản nữa"]})
    assert all(c.scope != "seafood" for c in build(prof, [], "tìm hải sản").hard)


def test_diet_break_in_prior_turn_retires_durable_diet():
    # durable note says chay, but a PRIOR user turn abandoned it → not enforced this turn.
    prof = NS(dietary=[], disliked_cuisines=[], context_memory={"notes": ["từ giờ tôi ăn chay"]})
    cs = build(prof, [U("tôi bỏ chay rồi"), A("ok")], "tìm phở")
    assert all(c.scope != "chay" for c in cs.hard)


def test_session_window_counts_user_turns_not_all():
    # 9 agent turns + 1 user diet declaration → the user turn is still recalled because we filter
    # to USER turns BEFORE the 8-slice (old code halved the window with interleaved agent turns).
    turns = [U("nay tôi ăn chay")] + [A(f"gợi ý {i}") for i in range(9)]
    assert any(c.scope == "chay" for c in build(None, turns, "tìm phở").hard)


def test_durable_marker_in_session_turn_honored():
    # 'từ giờ ... chay trường' in the current message → persistence durable (flag no longer discarded).
    cs = build(None, [], "Từ giờ nhớ tôi ăn chay trường nhé")
    assert any(c.scope == "chay" and c.persistence == "durable" for c in cs.hard)
