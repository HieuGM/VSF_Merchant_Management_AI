"""Profile-based ranking signals (phase-02) — pure functions, no DB, no side effects.

``profile_score`` returns a SMALL additive boost/penalty (signed float) summed into
``match_score``. ``should_hard_filter`` drops a merchant entirely (default off). Both are
no-ops on an empty/None profile. Vietnamese is diacritics-folded + the ``món `` prefix is
stripped for cuisine matching (``"Món Việt"`` ≡ ``"việt"``). ``budget_level`` (en) is mapped
to ``merchant_profiles.price_level`` (vi: ``rẻ`` / ``trung bình`` / ``cao cấp`` — the CHECK
constraint in database/models.py)."""
from __future__ import annotations

from core.text_norm import fold_diacritics
from typing import Any

from core.ranking_config import RankingConfig

# user budget_level (en) -> merchant_profiles.price_level (vi). The DB CHECK constraint
# (models.py MerchantProfile) restricts price_level to these three Vietnamese values.
_BUDGET_TO_PRICE: dict[str, str] = {
    "student": "rẻ",
    "standard": "trung bình",
    "premium": "cao cấp",
}
# Dietary vegetarian signals (matched against profile.dietary, then against merchant
# cuisine/taste_tags). "chay" is the canonical Vietnamese vegetarian marker.
_DIETARY_CHAY: tuple[str, ...] = ("chay", "vegetarian")


def _fold(s: str | None) -> str:
    """Diacritics-fold + strip the ``món `` category prefix for cuisine matching.

    Delegates the fold to ``core.text_norm.fold_diacritics`` (audit #15 — single source of
    truth) and adds the cuisine-specific ``món `` prefix strip ('Món Việt' → 'viet')."""
    folded = fold_diacritics(s)
    if folded.startswith("mon "):
        folded = folded[4:]
    return folded.strip()


def _cuisines_overlap(a: str, b: str) -> bool:
    """True if either folded cuisine is a substring of the other (handles 'việt' vs 'Món Việt')."""
    fa, fb = _fold(a), _fold(b)
    return bool(fa and fb and (fa in fb or fb in fa))


def profile_score(merchant: Any, profile: Any, cfg: RankingConfig) -> float:
    """Small additive score (may be negative) reflecting taste-profile fit. 0 = no signal.

    ``profile`` is a ``UserProfilePublic`` (or None); ``merchant`` is the ORM ``Merchant``
    (uses .cuisine, .taste_tags, .profile.price_level — all eagerly loaded by the repo)."""
    if profile is None:
        return 0.0
    score = 0.0
    cuisine = getattr(merchant, "cuisine", None)

    # --- Budget: user budget_level (en) maps to vi price_level; exact match -> boost ---
    budget = getattr(profile, "budget_level", None)
    if budget:
        want = _BUDGET_TO_PRICE.get(budget)
        prof = getattr(merchant, "profile", None)
        have = getattr(prof, "price_level", None) if prof else None
        if want and have and _fold(want) == _fold(have):
            score += cfg.w_budget

    # --- Liked cuisines: overlap -> boost, capped at liked_cap hits ---
    liked = getattr(profile, "liked_cuisines", None) or []
    if liked and cuisine:
        hits = sum(1 for c in liked if _cuisines_overlap(c, cuisine))
        score += cfg.w_liked * min(hits, cfg.liked_cap)

    # --- Disliked cuisines: overlap -> single penalty ---
    disliked = getattr(profile, "disliked_cuisines", None) or []
    if disliked and cuisine and any(_cuisines_overlap(c, cuisine) for c in disliked):
        score -= cfg.w_disliked

    # --- Dietary (chay): user wants vegetarian AND merchant has a veg signal -> boost ---
    dietary = getattr(profile, "dietary", None) or []
    if dietary and any(k in " ".join(dietary).lower() for k in _DIETARY_CHAY):
        tags = [cuisine] + list(getattr(merchant, "taste_tags", None) or [])
        hay = " ".join(_fold(t) for t in tags)
        if any(k in hay for k in _DIETARY_CHAY):
            score += cfg.w_dietary

    return score


def should_hard_filter(merchant: Any, profile: Any, cfg: RankingConfig) -> bool:
    """True only when ``hard_filter_disliked`` is on AND the merchant's cuisine is disliked.

    Default off (soft penalty only) — conservative: avoids nuking whole result sets when a
    disliked cuisine is common. Flip the flag to make dislikes a hard exclude."""
    if not cfg.hard_filter_disliked or profile is None:
        return False
    disliked = getattr(profile, "disliked_cuisines", None) or []
    cuisine = getattr(merchant, "cuisine", None)
    if not disliked or not cuisine:
        return False
    return any(_cuisines_overlap(c, cuisine) for c in disliked)
