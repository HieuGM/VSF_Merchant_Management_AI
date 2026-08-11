"""Deep-memory followup-resolution layer — what are you referring to?

Deterministic anaphora/followup routing (no coordinator): _is_anaphora_followup (skip fresh
search vs explanation followup), _prior_merchants (most-recent agent results), _name_match_targets
(name → merchant_id via trigram/bigram/distinctive-token, generic cuisine excluded),
_references_prior (gates prior_context injection so an unrelated prior can't leak), and
_resolve_followup_targets (ordinal/count/ambiguous → merchant_ids). Pure, no DB."""
from __future__ import annotations

from flows.customer_flow import (
    _is_anaphora_followup,
    _name_match_targets,
    _prior_merchants,
    _references_prior,
    _resolve_followup_targets,
)


def _agent(results):
    return {"sender": "agent", "payload": {"results": results}}


def _merch(mid, name, cuisine="Việt"):
    return {"merchant_id": mid, "name": name, "cuisine": cuisine}


# --- _is_anaphora_followup: anaphor AND attribute, NOT a refinement ---
def test_is_anaphora_followup_true_on_anaphor_plus_attribute():
    assert _is_anaphora_followup("giá của quán đầu tiên") is True       # anaphor + 'gia'
    assert _is_anaphora_followup("quán đó có cay không") is True        # 'quan do' + 'cay'
    assert _is_anaphora_followup("món này bao nhiêu tiền") is True      # 'mon nay' + 'bao nhieu'


def test_is_anaphora_followup_false_on_refinement_or_fresh_search():
    # Refinement marker wins → stays on the SEARCH path (wants new results).
    assert _is_anaphora_followup("còn quán khác rẻ hơn") is False       # 'khac'/'re hon'
    assert _is_anaphora_followup("quán đó rẻ hơn nữa") is False
    # Fresh search — no anaphor at all.
    assert _is_anaphora_followup("tìm quán phở gần Cầu Giấy") is False
    assert _is_anaphora_followup("") is False
    assert _is_anaphora_followup(None) is False


# --- _prior_merchants: most recent agent turn's results ---
def test_prior_merchants_most_recent_agent_turn():
    turns = [
        _agent([_merch("m1", "Cũ")]),
        {"sender": "user", "text": "x"},
        _agent([_merch("m2", "Mới"), _merch("m3", "Mới 2")]),
    ]
    out = _prior_merchants(turns)
    assert [m["merchant_id"] for m in out] == ["m2", "m3"]   # newest, not the first
    assert _prior_merchants([]) == []
    assert _prior_merchants([{"sender": "user", "text": "x"}]) == []


# --- _name_match_targets: distinctive name fragment → merchant_id ---
def test_name_match_distinctive_token_and_excludes_generic():
    prior = [_agent([_merch("m1", "Trà Sữa Tocotoco")])]
    # Distinctive brand token (len>=5) → match.
    assert _name_match_targets("tocotoco ở đâu", prior) == ["m1"]
    # Generic cuisine-only reference ('trà sữa') → ambiguous across that cuisine → no match.
    assert _name_match_targets("quán trà sữa kia", prior) == []


def test_name_match_non_generic_bigram_and_trigram():
    prior = [_agent([_merch("m1", "Như Thảo Quán"), _merch("m2", "Bún Đậu Mắm Tôm")])]
    # Non-generic bigram.
    assert _name_match_targets("như thảo giá bao nhiêu", prior) == ["m1"]
    # Trigram (3 tokens) — very specific.
    assert _name_match_targets("bún đậu mắm tôm có cay không", prior) == ["m2"]
    # No prior → nothing.
    assert _name_match_targets("tocotoco", []) == []


def test_name_match_distinctive_brand_vs_short_brand_precision():
    """Rule 3 (single distinctive token) matches brands INSIDE multi-token names — verified
    against the real merchant data (all 1625 names are multi-token, none single-word). A
    distinctive brand (len>=5) resolves; a short brand (len<5) intentionally does NOT.

    NOT a bug — the len(toks)<2 guard never fires on real data (0 single-token merchants), and
    the len>=5 threshold is a deliberate precision guard: short tokens like 'kfc'/'bbq' collide
    and would false-positive. The anaphora path ('quán đó') remains the fallback for short brands."""
    prior = [_agent([
        _merch("m_lot", "Gà Rán & Burger Lotteria - Hoàng Quốc Việt"),
        _merch("m_kfc", "Gà Rán KFC - Lê Văn Lương"),
    ])]
    # Distinctive brand token (len>=5) inside a multi-token name → matches.
    assert _name_match_targets("Lotteria giá bao nhiêu", prior) == ["m_lot"]
    # Short brand token (len<5) → does NOT match (precision guard; falls back to anaphora).
    assert _name_match_targets("KFC kia có rẻ không", prior) == []


# --- _references_prior: gates prior_context injection ---
def test_references_prior_anaphor_refinement_or_name():
    # 'Highlands Coffee' is 2 tokens → eligible for name-match (single-token names are skipped).
    prior = [_agent([_merch("m1", "Highlands Coffee")])]
    assert _references_prior("quán đó giá sao", prior) is True          # anaphor
    assert _references_prior("rẻ hơn nữa nhé", prior) is True           # refinement
    assert _references_prior("highlands có ổn không", prior) is True    # name match (distinctive token)
    # A TRULY fresh search (none of the three) → False → prior_context stays '' (no leak).
    assert _references_prior("tìm phở gần đây", prior) is False
    assert _references_prior("tìm phở", None) is False
    assert _references_prior(None, prior) is False


# --- _resolve_followup_targets: ordinal / count / ambiguous resolution ---
def test_resolve_followup_ordinals_and_counts():
    four = [_agent([_merch(f"m{i}", f"Q{i}") for i in range(4)])]
    assert _resolve_followup_targets("giá quán đầu tiên", four) == ["m0"]
    assert _resolve_followup_targets("quán thứ hai có cay không", four) == ["m1"]
    assert _resolve_followup_targets("quán thứ tư đó", four) == ["m3"]
    assert _resolve_followup_targets("so sánh 2 quán", four) == ["m0", "m1"]      # count top-2
    assert _resolve_followup_targets("so sánh cả 2", four) == ["m0", "m1"]        # 'ca 2'
    assert _resolve_followup_targets("quán cuối cùng giá sao", four) == ["m3"]


def test_resolve_followup_ambiguous_defaults_top_three():
    # 'quán đó' over several results, no ordinal/count → list top-3 (agent lists + asks which).
    four = [_agent([_merch(f"m{i}", f"Q{i}") for i in range(4)])]
    assert _resolve_followup_targets("quán đó có ổn không", four) == ["m0", "m1", "m2"]
    # No agent results at all → nothing to resolve.
    assert _resolve_followup_targets("quán đó giá bao nhiêu", []) == []
    assert _resolve_followup_targets("quán đó", [{"sender": "user", "text": "x"}]) == []
