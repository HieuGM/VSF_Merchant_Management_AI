"""Unit tests for core/query_relevance — the graded merchant-relevance scorer.

Guards the 3 fixes: (1) tone-aware name match kills the phở/phố collision, (2) graded scoring
differentiates a name match from a menu-only hit, (3) multi-word queries match across
punctuation. Pure functions."""
from __future__ import annotations

from core.query_relevance import name_token_match, query_relevance


# --- name_token_match: tone-aware, rejects place collisions ---
def test_name_match_real_food_vs_place_collision():
    # 'phở' (food) must NOT ride on 'Phố' (street) — the original false match.
    assert name_token_match("pho", "Cơm Tấm Phố Cổ") is False
    assert name_token_match("pho", "Phố Cổ Mã Mây") is False
    # but a real phở name matches (toneless 'pho' still works; name_token_match takes a FOLDED token).
    assert name_token_match("pho", "Phở Bò Tám Lâm") is True
    # query_relevance folds the query itself, so a toned 'phở' query also matches a 'Phở' name.
    from core.query_relevance import query_relevance as qr
    assert qr("phở", "Phở Gà Thuỷ Béo", "Món Việt") == 0.65


def test_name_match_strips_punctuation():
    # Attached punctuation ('rán,') must not break a multi-token name match.
    assert name_token_match("ran", "3 Râu - Gà Rán, Pizza") is True
    assert name_token_match("ga", "3 Râu - Gà Rán, Pizza") is True


def test_name_match_other_place_tokens_rejected():
    # đường/quận/ngõ also collide-prone → rejected as food matches.
    assert name_token_match("duong", "Phở Bò Đường Nguyễn Huệ") is False
    assert name_token_match("ran", "Gà Rán") is True  # normal food token unaffected


# --- query_relevance: graded, differentiates name vs menu vs nothing ---
def test_relevance_name_match_beats_menu_only():
    name_match = query_relevance("phở", "Phở Bò", "Món Việt")
    menu_only = query_relevance("phở", "3 Râu - Gà Rán", "Món Việt", menu_matched=True)
    nothing = query_relevance("phở", "Quán Nước", "Đồ uống")
    assert name_match > menu_only > nothing
    assert name_match == 0.65            # full name match, no cuisine/menu bonus
    assert menu_only == 0.10             # only the weak menu signal
    assert nothing == 0.0


def test_relevance_multi_word_proportional():
    # Both tokens match → full; one of two → half.
    assert query_relevance("gà rán", "3 Râu - Gà Rán, Pizza", "Món Việt") == 0.65
    assert 0.30 < query_relevance("bún chả", "Bún Bò Huế", "Món Việt") < 0.40  # only 'bún' matches


def test_relevance_cuisine_and_taste_tag_match():
    # 'chay' not in name but in taste_tags → partial credit via cui_frac.
    rel = query_relevance("chay", "An Lạc Quán", "Việt", taste_tags=["đồ chay"])
    assert 0.0 < rel <= 0.25  # cuisine/tag contributes, name does not


def test_relevance_empty_query():
    assert query_relevance("", "Phở", "Việt") == 0.0
    assert query_relevance(None, "Phở", "Việt") == 0.0


# --- audited fixes: place-token stoplist (ga/ca) + tokenized cui_frac ---
def test_ga_station_does_not_match_chicken_query():
    # 'ga' (train station) folds identically to 'gà' (chicken); the station token is now stopped.
    assert name_token_match("ga", "Quán Gần Ga Hà Nội") is False   # 'Ga' = station → blocked
    assert name_token_match("ga", "Gà Rán 3 Râu") is True          # 'gà' = chicken (toned) → kept


def test_cui_frac_uses_whole_token_not_substring():
    # A 2-char folded food token must not substring-match inside an unrelated cuisine/tag word.
    # 'ca' (from cá=fish) is a substring of 'cay'/'canh' but not a whole token → no cuisine credit.
    assert query_relevance("cá", "Cơm Niêu", "Món Cay") == 0.0    # was 0.25 via 'ca'⊂'cay'
    assert query_relevance("mì", "Bún Mộc", "Món Miến") == 0.0    # was 0.25 via 'mi'⊂'miến'
    # sanity: a real token cuisine match still scores.
    assert query_relevance("cay", "Quán Nước", "Món Cay") > 0.0
