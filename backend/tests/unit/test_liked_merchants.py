"""Unit tests for episodic-memory ranking (phase-05) — liked-merchant boosts. Pure, no DB.

Covers the profile_score episodic branches (services/profile_ranking.py): a directly-liked
merchant gets a strong boost, and a merchant sharing cuisine with a liked merchant gets the
liked-cuisine boost via the union (liked_cuisines ∪ liked_merchant_cuisines) — this is what
powers 'gợi ý giống quán từng thích'. Repo idempotency is covered by the live API check."""
from __future__ import annotations

from types import SimpleNamespace

from core.ranking_config import RankingConfig
from models.preference import UserProfilePublic
from services.profile_ranking import profile_score

CFG = RankingConfig()


def _m(merchant_id=None, cuisine=None, taste_tags=None) -> SimpleNamespace:
    """Merchant stand-in including merchant_id (profile_score reads it for the liked branch)."""
    return SimpleNamespace(
        merchant_id=merchant_id,
        cuisine=cuisine,
        taste_tags=taste_tags or [],
        profile=SimpleNamespace(price_level=None),
    )


def test_directly_liked_merchant_gets_boost():
    p = UserProfilePublic(user_id="u", liked_merchant_ids=["m1"])
    liked = profile_score(_m("m1", "Việt"), p, CFG)
    other = profile_score(_m("m2", "Việt"), p, CFG)
    assert liked == other + CFG.w_liked_merchant  # exactly the direct boost above the unliked one
    assert other == 0.0  # no other signal for the unliked merchant


def test_liked_merchant_cuisine_boosts_similar():
    # The user liked a 'Nhật' merchant → its cuisine flows into liked_merchant_cuisines → a
    # DIFFERENT sushi merchant (same cuisine, NOT directly liked) rises. This is the
    # 'gợi ý giống quán từng thích' effect.
    p = UserProfilePublic(user_id="u", liked_merchant_cuisines=["nhật"])
    assert profile_score(_m("mX", "Nhật"), p, CFG) > 0.0
    assert profile_score(_m("mY", "Việt"), p, CFG) == 0.0  # unrelated cuisine — no boost


def test_direct_like_and_its_cuisine_stack():
    # The liked merchant itself gets BOTH the direct boost AND its own cuisine (union) boost.
    p = UserProfilePublic(user_id="u", liked_merchant_ids=["m1"], liked_merchant_cuisines=["việt"])
    score = profile_score(_m("m1", "Món Việt"), p, CFG)
    assert score == CFG.w_liked_merchant + CFG.w_liked  # direct + 1 cuisine hit (folded 'viet')


def test_union_does_not_double_count_explicit_liked_cuisine():
    # If a cuisine is in BOTH liked_cuisines and liked_merchant_cuisines, the union dedupes —
    # no double boost (a set, not a sum over both lists).
    p = UserProfilePublic(
        user_id="u", liked_cuisines=["nhật"], liked_merchant_cuisines=["nhật"]
    )
    once = profile_score(_m("mX", "Nhật"), p, CFG)
    assert once == CFG.w_liked  # a single cuisine hit, not 2×
