"""Constraint catalog — the single source of truth for user dietary/allergen restrictions.

Replaces the scattered lexicons that drove per-case filters (see git history). A restriction
SCOPE (e.g. "seafood", "chay") is defined ONCE here with its CANONICAL (diacritic-preserving)
synonyms + enforcement kind. Adding a restriction type = adding one ``ConstraintDef`` row, NOT a
new regex/filter. The loader derives ``Constraint``s from this catalog; the enforcer consults the
catalog's ``terms`` + ``kind`` to decide keep/drop.

Kinds:
  - ``avoid`` (allergy): drop a merchant if the allergen APPEARS (cuisine/name → always; dishes →
    only if EVERY visible dish is the allergen, so a mixed restaurant with ≥1 safe dish survives).
  - ``want``  (diet, e.g. chay): drop a merchant if the diet signal is ABSENT everywhere.

MATCHING IS COLLISION-SAFE (``scope_present``). Vietnamese folds tones away, merging many
unrelated words to the same ASCII token (cua≈của, ghẹ≈ghế, mực≈mục, sò≈so-sánh, chay≈chạy, and
substrings ốc⊂ngọc/tóc/độc, sò⊂sốt). A bare ``term in folded_text`` check (the old matcher)
false-fired on all of these — dropping 'Cơm Của Mẹ' or 'Nhà hàng Ngọc' for a seafood-allergic
user, or force-vegetarian-filtering a jogger who said 'chạy bộ'. ``scope_present`` instead:
  - long / multi-word terms (hải sản, tôm hùm, sushi): phrase match on folded (unambiguous);
  - short single-word terms: WHOLE-TOKEN match on folded (kills substring hits sốt⊃sò, ngọc⊃ốc);
  - the handful of TRUE homophones (folded token shared with a common non-target word): ALSO
    require the canonical diacritic form in the RAW text (cua≠của, ghẹ≠ghế, mực≠mục, sò≠so-sánh,
    chay≠chạy). Canonical forms that are themselves toneless (cua, chay) still accept toneless
    typing; toned canonicals (ghẹ, mực, sò) sacrifice rare toneless typing to kill the false drop.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from core.text_norm import fold_diacritics

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)  # word chars incl. VN letters + digits; strips punctuation

# Short folded terms that are TRUE homophones with a common non-target word. A folded whole-token
# hit on one of these is NOT enough — confirm the canonical (diacritic) form is actually present.
# Map: folded_term -> canonical diacritic form to require in the RAW (unfolded, lowercased) text.
# Toneless canonicals (cua, chay) still match toneless typing; toned canonicals (ghẹ, mực, sò) do not.
_HOMOPHONE_CANONICAL: dict[str, str] = {
    "cua": "cua",   # crab (toneless) vs của (possessive 'of')
    "ghe": "ghẹ",   # mud crab vs ghế (chair) / ghê (intensifier 'cay ghê')
    "muc": "mực",   # squid vs mục (purpose) / mức (level)
    "so": "sò",     # clam vs so (compare 'so sánh') — also killed as a substring of sốt by tokenizing
    "chay": "chay", # vegetarian (toneless) vs chạy (run 'chạy bộ')
    "sua": "sữa",   # milk vs sửa (fix 'sửa xe') / sủa (bark) — dairy needs the diacritic form
    "lac": "lạc",   # peanut vs lạc (obsolete 'lạc hậu') / lắc (shake 'lắc phô mai') — see note below
}

# Common ABBREVIATIONS users type (8.3 stress case: 'HS' = hải sản). Expanded BEFORE folding so
# the catalog matcher sees the full form. Keys folded; whole-word replace only (avoid hitting
# inside longer words); applied on the RAW text (lowercased) in normalize_abbreviations().
_ABBREVIATIONS: tuple[tuple[str, str], ...] = (
    ("hs", "hải sản"),
)


@dataclass(frozen=True)
class ConstraintDef:
    """Static definition of one restriction scope."""

    scope: str                   # canonical id, e.g. "seafood", "chay"
    label_vi: str                # Vietnamese label for the explanation prompt
    terms: tuple[str, ...]       # CANONICAL (diacritic-preserving) synonyms
    kind: str                    # "avoid" (allergy) | "want" (diet)


# Seafood-allergen terms (shellfish + sushi-grade fish carriers), CANONICAL diacritic forms.
# Bare "cá" (fish) is intentionally excluded — too broad; shellfish/sushi are the medically
# high-risk carriers a seafood-allergic user must avoid.
_SEAFOOD_TERMS: tuple[str, ...] = (
    "hải sản", "cua", "ghẹ", "mực", "ngao", "nghêu", "ốc", "sò",  # shellfish (NO tôm — own scope)
    "sushi", "sashimi",                                            # sushi-grade (high seafood cross-risk)
)
_CHAY_TERMS: tuple[str, ...] = ("chay", "vegetarian")

# --- NEW SCOPES (memory-eval 260813 khuyến nghị #1 + #5; data-probed against the 1625-merchant
# corpus + 99k menu_items before term selection — homophone-prone tokens measured and EXCLUDED):
#   - peanut: NO 'lạc' despite being a common synonym — folds to 'lac' which collides with
#     'lắc' (lắc phô mai, ~1000 false dish hits) and street names (Lạc Trung, Lạc Long Quân).
#     'đậu phộng' (phrase, unambiguous) + 'peanut' cover the real carriers (55 true dishes).
#   - dairy: 'sữa' kept as a HOMOPHONE canonical (needs diacritic — sửa/sủa false positives);
#     'phô mai'/'cheese' phrase+token are unambiguous (4857 dishes, all true).
#   - gluten: no 'mì' alone (mì = noodles generally, folds 'mi' ⊂ mien/mien… too broad);
#     phrase forms only ('mì Ý', 'spaghetti', 'bánh mì kẹp' — 66 merchants, 340 dishes).
#   - organ_meat: NO 'lòng' — collides with Ô long tea + proper names (Hoàng Long, 20 mostly-false
#     merchant hits); 'nội tạng'/'tiết canh'/'trứng vịt lộn' are unambiguous phrases.
#   - shrimp: split OUT of seafood (eval 2.2 — dị ứng tôm but likes other seafood was
#     over-excluded). seafood no longer carries 'tôm'/'tôm hùm'; this scope does.
_PEANUT_TERMS: tuple[str, ...] = ("đậu phộng", "bơ đậu phộng", "peanut")
_DAIRY_TERMS: tuple[str, ...] = ("sữa", "phô mai", "bơ sữa", "cheese")
_GLUTEN_TERMS: tuple[str, ...] = ("gluten", "bánh mì kẹp", "mì Ý", "spaghetti")
_ORGAN_MEAT_TERMS: tuple[str, ...] = ("nội tạng", "tim gan", "tiết canh", "trứng vịt lộn")
_SHRIMP_TERMS: tuple[str, ...] = ("tôm", "tôm hùm")

# The catalog. Extensible — new restriction = new row. Terms kept in their canonical diacritic
# form (NOT pre-folded) so the collision-safe matcher can re-check homophones against raw text.
CATALOG: dict[str, ConstraintDef] = {
    "seafood": ConstraintDef("seafood", "hải sản", _SEAFOOD_TERMS, "avoid"),
    "chay": ConstraintDef("chay", "đồ chay", _CHAY_TERMS, "want"),
    "shrimp": ConstraintDef("shrimp", "tôm", _SHRIMP_TERMS, "avoid"),
    "peanut": ConstraintDef("peanut", "đậu phộng", _PEANUT_TERMS, "avoid"),
    "dairy": ConstraintDef("dairy", "sữa/phô mai", _DAIRY_TERMS, "avoid"),
    "gluten": ConstraintDef("gluten", "gluten/bánh mì", _GLUTEN_TERMS, "avoid"),
    "organ_meat": ConstraintDef("organ_meat", "nội tạng", _ORGAN_MEAT_TERMS, "avoid"),
}


# Scope HIERARCHY: declaring a PARENT allergy also enforces the CHILD scopes (medical reality —
# a general seafood allergy includes shellfish, so 'dị ứng hải sản' must still drop tôm places
# even though 'tôm' moved to its own scope for the 2.2 shrimp-only case). One direction only:
# declaring the CHILD ('dị ứng tôm') does NOT impose the parent — that is exactly the 2.2 fix.
_SCOPE_CHILDREN: dict[str, tuple[str, ...]] = {
    "seafood": ("shrimp",),
}


def expand_child_scopes(scopes: list[str]) -> list[str]:
    """Add each fired scope's children (dedup, order-stable). Used by the loader after scope
    detection so parent declarations enforce the narrower scopes too."""
    out = list(scopes)
    for s in scopes:
        for child in _SCOPE_CHILDREN.get(s, ()):
            if child in CATALOG and child not in out:
                out.append(child)
    return out


def normalize_abbreviations(text: str | None) -> str:
    """Expand user-typed abbreviations (whole-word) so the catalog matcher sees full forms.

    Eval 8.3: 'mình dị ứng HS' — the note stored fine but no scope fired because the catalog
    matcher looks for 'hải sản'/'tôm'… tokens. Expansion matches on the LOWERCASED text but
    returns the ORIGINAL text unchanged when nothing fires — health-notes are surfaced
    verbatim (test: 'Tôi bị dị ứng tôm' must not come back lowercased)."""
    if not text:
        return text or ""
    import re as _re
    for short, full in _ABBREVIATIONS:
        if _re.search(rf"\b{_re.escape(short)}\b", text.lower()):
            return _re.sub(rf"\b{_re.escape(short)}\b", full, text.lower())
    return text


def _term_present(
    term_raw: str, text_raw_lower: str, folded_tokens: frozenset[str], text_folded: str
) -> bool:
    """Collision-safe presence test for ONE canonical term against a haystack.

    See module docstring for the long/short/homophone strategy. ``text_raw_lower`` is the
    unfolded lowercased haystack (for the homophone diacritic re-check); ``folded_tokens`` and
    ``text_folded`` are its diacritics-folded forms."""
    ft = fold_diacritics(term_raw)
    if not ft:
        return False
    # Multi-word terms (hải sản, tôm hùm): unambiguous → phrase match on folded.
    if " " in ft:
        return ft in text_folded
    # Single-word term (any length — sushi, sashimi, cua, chay, ốc): whole-token match on folded
    # (kills substring hits sốt⊃sò, ngọc⊃ốc, nước⊃ốc), then a homophone diacritic re-check.
    if ft not in folded_tokens:
        return False
    canon = _HOMOPHONE_CANONICAL.get(ft)
    if canon is None:
        return True  # unambiguous short token (tôm→tom, ốc→oc, ngao, nghêu)
    # True homophone: require the canonical diacritic form VERBATIM in the raw (unfolded) text. This
    # is the ONLY way to tell crab(cua) from của(of), vegetarian(chay) from chạy(run) — they fold to
    # the same token but differ in diacritics. Toneless typing for cua/chay still works because their
    # canonical IS the toneless form ('cua'/'chay' appear verbatim in a toneless user text). Toned
    # canonicals ghẹ/mực/sò sacrifice rare toneless typing to kill the ghế/mục false positives.
    return canon in text_raw_lower


def scope_present(cdef: ConstraintDef, text_raw: str, text_folded: str) -> bool:
    """True if any of the scope's canonical terms is present in the text — collision-safe.

    Used by BOTH the loader (declaration detection on user text) and the enforcer (allergen
    presence on merchant cuisine/name/dishes). Pass the SAME text in both forms: raw (original
    diacritics, lowercased) + folded (diacritics stripped)."""
    if not cdef.terms:
        return False
    raw_l = (text_raw or "").lower()
    toks = frozenset(_TOKEN_RE.findall(text_folded or ""))
    return any(_term_present(t, raw_l, toks, text_folded or "") for t in cdef.terms)


def merchant_cuisine_name(merchant: dict) -> str:
    """Folded L1 haystack: cuisine + name + taste_tags (no dishes). Used by the DB-result filter
    (should_hard_filter), where menu items are not yet loaded."""
    bits = [merchant.get("cuisine"), merchant.get("name")]
    bits += list(merchant.get("taste_tags") or [])
    return fold_diacritics(" ".join(str(b) for b in bits if b))


def merchant_cuisine_raw(merchant: dict) -> str:
    """RAW (unfolded, lowercased) L1 haystack — the diacritic source for homophone re-checks."""
    bits = [merchant.get("cuisine"), merchant.get("name")]
    bits += list(merchant.get("taste_tags") or [])
    return " ".join(str(b) for b in bits if b).lower()


def merchant_dishes(merchant: dict) -> str:
    """Folded dish-name haystack (top_dishes / top_menu_items). Empty when not loaded."""
    dishes = merchant.get("top_dishes") or merchant.get("top_menu_items") or []
    return fold_diacritics(" ".join(str(d.get("name", "")) if isinstance(d, dict) else str(d) for d in dishes))


def merchant_dishes_raw(merchant: dict) -> str:
    """RAW (unfolded, lowercased) dish-name haystack — diacritic source for homophone re-checks."""
    dishes = merchant.get("top_dishes") or merchant.get("top_menu_items") or []
    return " ".join(
        str(d.get("name", "")) if isinstance(d, dict) else str(d) for d in dishes
    ).lower()


def all_dish_names(merchant: dict) -> list[str]:
    """Folded individual dish names (for the 'every dish is the allergen' partial-overlap test)."""
    dishes = merchant.get("top_dishes") or merchant.get("top_menu_items") or []
    return [fold_diacritics(str(d.get("name", "")) if isinstance(d, dict) else str(d)) for d in dishes]
