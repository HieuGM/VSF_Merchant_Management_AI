"""Vietnamese vague-descriptor → search-arg expansion (Path A / phase-01).

WHY: the CrewAI coordinator already decomposes user text into the structured args
(`query`/`cuisine`/`city`/...) that ``merchant_search`` consumes, but VAGUE descriptors
("ăn gì cho đỡ ngán", "món thanh đạm", "trời lạnh thèm lẩu", "chill chill") don't map
obviously to a dish or cuisine, so the LLM's mapping is inconsistent. This module gives
the search agent a deterministic, curated gloss: descriptor → suggested ``query`` dish
keywords + a REAL ``cuisine`` category.

WHY QUERY KEYWORDS + CUISINE (NOT taste_tags): ``merchant_search`` has NO taste_tags arg
(its args are query/cuisine/city/price/rating). taste_tags only help at RANKING time
(``query_relevance`` scores tag-overlap), not RECALL (the SQL ILIKE matches name/cuisine/
menu only). So to improve RECALL the hint must suggest dish KEYWORDS for ``query`` (which
the ILIKE matches against merchant names/menus) + real cuisine values. The cuisines and
tags referenced below are grounded in the actual merchant_platform distribution (queried
2026-08-11): cuisines are coarse composite values (Món Việt / Quán ăn / Café-Dessert /
Ăn vặt-vỉa hè / Món Thái,Món Á / Nhà hàng); dish keywords are common VN terms that appear
in merchant names/menus (lẩu, phở, gỏi, canh, súp, chè, kem, trà, salad, bánh, buffet).

SSoT: key matching reuses ``core.text_norm.fold_diacritics`` (audit #15) — no fold logic
duplication. Matching is folded-SUBSTRING (advisory hints; a stray false-positive is
harmless because the LLM ignores irrelevant hints and the truth-first rules still bind).

Gated by ``settings.coordinator_descriptor_expansion_enabled`` (default False) — when off,
``expand_vague_descriptors`` is not even called and the search_task prompt is byte-identical
to baseline. Complementary to (not a duplicate of) ``_PREFERENCE_SIGNAL_KEYWORDS`` in
customer_flow.py: that list gates preference_task ROUTING; this expands the search_task QUERY.
"""
from __future__ import annotations

from core.text_norm import fold_diacritics

# Each entry: (folded_key, label, query_hint, cuisine_hint).
#   folded_key   — pre-folded ASCII (compared against fold_diacritics(user_query))
#   label        — original Vietnamese descriptor, shown in the hint for the LLM's context
#   query_hint   — dish keywords for the `query` arg (appear in merchant names/menus → recall)
#   cuisine_hint — a REAL cuisine value from the merchant_platform distribution
# Keys are ≥2 syllables (or unambiguous) to avoid bare-token collisions ("cay"→use "do cay").
_DESCRIPTORS: tuple[tuple[str, str, str, str], ...] = (
    ("do ngan",    "đỡ ngán",     "gỏi cuốn salad thanh đạm",  "Món Việt"),
    ("giam ngan",  "giảm ngán",   "gỏi cuốn salad thanh đạm",  "Món Việt"),
    ("thanh dam",  "thanh đạm",   "gỏi cuốn canh salad",       "Món Việt"),
    ("nhe nhang",  "nhẹ nhàng",   "gỏi canh salad",            "Món Việt"),
    ("an kieng",   "ăn kiêng",    "salad gỏi ức gà healthy",   "Món Việt"),
    ("eat clean",  "eat clean",   "salad gỏi healthy",         "Món Việt"),
    ("giam can",   "giảm cân",    "salad gỏi healthy ít béo",  "Món Việt"),
    ("do nhe",     "đồ nhẹ",      "bánh trà snack",            "Ăn vặt/vỉa hè"),
    ("an vat",     "ăn vặt",      "bánh trà snack",            "Ăn vặt/vỉa hè"),
    ("do cay",     "đồ cay",      "lẩu thái cay tứ xuyên",     "Món Thái, Món Á"),
    ("an cay",     "ăn cay",      "lẩu thái cay tứ xuyên",     "Món Thái, Món Á"),
    ("do ngot",    "đồ ngọt",     "chè kem bánh tráng miệng",  "Café/Dessert"),
    ("trang mieng","tráng miệng", "chè kem bánh tráng miệng",  "Café/Dessert"),
    ("do uong",    "đồ uống",     "trà cà phê trà sữa",        "Café/Dessert"),
    ("dai bo",     "đại bổ",      "lẩu súp canh",              "Món Việt"),
    ("bo duong",   "bổ dưỡng",    "lẩu súp canh",              "Món Việt"),
    ("dam da",     "đậm đà",      "lẩu nướng thịt nướng",      "Quán ăn"),
    ("no ne",      "no nê",       "lẩu nướng buffet",          "Quán ăn"),
    ("troi lanh",  "trời lạnh",   "lẩu súp phở canh",          "Món Việt"),
    ("troi nong",  "trời nóng",   "trà kem chè trà chanh",     "Café/Dessert"),
    ("troi mua",   "trời mưa",    "lẩu canh",                  "Món Việt"),
    ("chill",      "chill",       "cà phê trà cafe",           "Café/Dessert"),
    ("nhom",       "nhóm",        "lẩu nướng buffet",          "Quán ăn"),
    ("nhau",       "nhậu",        "mồi nhậu bia",              "Quán ăn"),
)


def expand_vague_descriptors(query: str | None) -> str:
    """Vietnamese hint string for any vague descriptor in ``query`` ("" when none).

    Advisory text for the search_task prompt: suggests concrete ``query`` dish keywords +
    a real ``cuisine`` so the LLM maps a vague descriptor to searchable terms consistently.
    Multiple matches join with '; '. No match / empty query → "" (caller renders "(không có)"
    so the prompt line is a no-op)."""
    if not query:
        return ""
    folded = fold_diacritics(query)
    if not folded:
        return ""
    hits = [
        f"{label} → query: {q_hint}, cuisine: {c_hint}"
        for key, label, q_hint, c_hint in _DESCRIPTORS
        if key in folded
    ]
    return "; ".join(hits)
