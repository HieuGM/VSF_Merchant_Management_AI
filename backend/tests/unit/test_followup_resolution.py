"""Unit tests for flows.followup_resolution — deterministic follow-up/anaphora/refinement/
negation helpers (audit 260820 proposal #4: 5 stable-fail GT cases TC-10/25/28/39/41)."""
from __future__ import annotations

from flows.followup_resolution import (
    carries_negated_term,
    followup_needs_skip_search,
    is_bare_referent_followup,
    negation_filter_terms,
    refined_max_price,
)


# --- TC-41/25/39: bare-referent anaphors must skip the fresh search ---
def test_tc41_bare_ordinal_referent_is_followup():
    assert followup_needs_skip_search("Cái đầu tiên đó") is True

def test_tc25_on_khong_is_followup():
    assert followup_needs_skip_search("Quán này có ổn không?") is True

def test_tc39_the_nao_is_followup():
    assert followup_needs_skip_search("Sao chỉ có đúng 1 quán vậy, quán này thế nào?") is True

def test_attr_gated_anaphor_still_followup():
    assert followup_needs_skip_search("Quán đầu tiên giá bao nhiêu?") is True


# --- regressions: fresh searches / refinements must NOT become follow-ups ---
def test_negation_search_not_followup():
    assert followup_needs_skip_search("Tìm quán ăn không cay, không phải đồ chiên, ở Thanh Xuân") is False

def test_food_dish_with_demonstrative_not_followup():
    # 'đồ chiên ở đâu ngon' — food token + question → fresh search
    assert is_bare_referent_followup("đồ chiên ở đâu ngon") is False

def test_tc10_cheaper_refinement_not_followup():
    assert followup_needs_skip_search("Rẻ hơn nữa được không") is False

def test_long_sentence_not_bare_referent():
    assert is_bare_referent_followup(
        "Cái đầu tiên đó giờ mở cửa tới mấy giờ và có giao hàng tới nhà không") is False

def test_plain_query_not_followup():
    assert followup_needs_skip_search("Tìm quán phở gần đây") is False


# --- TC-10: deterministic cheaper-refinement cap ---
def test_tc10_prior_40k_refines_to_30k():
    cap = refined_max_price("Rẻ hơn nữa được không",
                            ["Tìm quán cơm văn phòng gần Mỹ Đình dưới 40k"])
    assert cap == 30000

def test_refine_without_prior_price_is_none():
    assert refined_max_price("Rẻ hơn nữa được không", ["Tìm quán cơm ngon"]) is None

def test_non_price_query_is_none():
    assert refined_max_price("Quán nào ngon hơn", ["dưới 40k"]) is None

def test_refine_uses_latest_prior_price():
    cap = refined_max_price("Rẻ hơn nữa", ["dưới 100k", "quán cơm dưới 50k thôi"])
    assert cap == max(15000, int(50000 * 0.75))


# --- TC-28: negation term extraction + post-filter ---
def test_tc28_extracts_both_negated_terms():
    terms = negation_filter_terms("Tìm quán ăn không cay, không phải đồ chiên, nhưng cũng đừng quá rẻ, ở Thanh Xuân")
    assert set(terms) == {"cay", "chien"}

def test_tc28_drops_fried_spicy_result():
    terms = ["cay", "chien"]
    assert carries_negated_term({"name": "Gà Rán Cay", "cuisine": "Ăn nhanh"}, terms) is True

def test_tc28_keeps_clean_result():
    terms = ["cay", "chien"]
    assert carries_negated_term({"name": "Phở Thìn", "cuisine": "Món Việt"}, terms) is False

def test_affirmative_spicy_query_no_negation():
    assert negation_filter_terms("Tìm quán cay ngon") == []

def test_taste_tags_counted_in_negation():
    assert carries_negated_term({"name": "Quán X", "cuisine": None, "taste_tags": ["cay"]}, ["cay"]) is True
