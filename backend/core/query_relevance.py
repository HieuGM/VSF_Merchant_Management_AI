"""Graded query-relevance scoring for merchants.

Replaces the coarse 3-step (1.0/0.7/0.4) + bare-substring matchers in merchant_search_service.
Two problems that motivated this:

  1. False match — folding strips Vietnamese tones, so 'phở' (noodle) ≡ 'phố' (street) ≡ 'pho'.
     A bare ``q in name`` check then treated 'Cơm Tấm **Phố** Cổ' as a perfect name match for a
     'phở' query. ``name_token_match`` is TONE-AWARE: a folded match is rejected when the matched
     name token is a place word (phố/đường/quận/…), so a food query no longer rides on a street
     name. Toneless typing still works ('pho' → 'phở' name token) because only the PLACE form is
     blocked, not the food form.

  2. No differentiation — a name match and a menu-only hit scored ~the same (name +0.20 vs menu
     +0.15), while constant merchant signals (rating/overall/cuisine) dominated. So a chicken
     place with phở on the menu ranked ~equal to a real phở shop. ``query_relevance`` makes the
     NAME the primary, graded signal; menu is a weak tiebreak."""
from __future__ import annotations

import re

from core.text_norm import fold_diacritics as fold

# Original-tone name tokens that denote PLACES, not foods. After folding they collide with food
# words (phố → 'pho' ≡ phở → 'pho'), so a folded match on one is a false positive — the user asked
# for the food, not the street/district. Blocking the place form (phố) but not the food form (phở)
# is what makes toneless 'pho' still match a real phở shop.
_PLACE_NAME_TOKENS = frozenset({
    "phố", "đường", "quận", "phường", "ngõ", "ngách", "khu", "làng", "dốc",
    "thị trấn", "xã", "huyện", "thôn", "kv",
})

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)  # word chars incl. VN letters + digits, strips punctuation


def name_token_match(q_token_folded: str, name_orig: str | None) -> bool:
    """True if a folded query token equals a folded NAME token — tone-aware (rejects place
    collisions: 'phố' won't satisfy a 'phở'/'pho' query). Tokenizes on \\w+ so attached punctuation
    ('rán,' → 'rán') doesn't break multi-word matches."""
    if not q_token_folded or not name_orig:
        return False
    for orig in _TOKEN_RE.findall(name_orig.lower()):
        if q_token_folded == fold(orig) and orig not in _PLACE_NAME_TOKENS:
            return True
    return False


def query_relevance(
    query: str | None, name: str | None, cuisine: str | None,
    taste_tags=(), menu_matched: bool = False,
) -> float:
    """Graded 0-1 relevance of a merchant to the query. NAME token match (tone-aware, strongest)
    > CUISINE/taste-tag match > menu-only. Differentiates a name match from a menu-only hit — the
    old scorer gave both nearly the same score, so relevance barely affected ranking."""
    if not query:
        return 0.0
    qtoks = [t for t in fold(query).split() if t]
    if not qtoks:
        return 0.0
    name_frac = sum(1 for t in qtoks if name_token_match(t, name)) / len(qtoks)
    cuif = fold(cuisine or "")
    tags = " ".join(fold(str(t)) for t in (taste_tags or []))
    cui_frac = sum(1 for t in qtoks if t in cuif or t in tags) / len(qtoks)
    # NAME dominates; cuisine/tags secondary; menu is a weak last resort.
    return 0.65 * name_frac + 0.25 * cui_frac + 0.10 * (1.0 if menu_matched else 0.0)
