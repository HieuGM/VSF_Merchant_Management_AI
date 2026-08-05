"""Unit tests for profile-based ranking signals (phase-02) — pure, no DB."""
from __future__ import annotations

from types import SimpleNamespace

from core.ranking_config import RankingConfig
from models.preference import UserProfilePublic
from services.profile_ranking import _fold, profile_score, should_hard_filter

CFG = RankingConfig()  # conservative defaults


def _merchant(cuisine=None, price_level=None, taste_tags=None) -> SimpleNamespace:
    """Lightweight Merchant stand-in (only the fields profile_ranking reads)."""
    return SimpleNamespace(
        cuisine=cuisine,
        taste_tags=taste_tags or [],
        profile=SimpleNamespace(price_level=price_level),
    )


def test_fold_strips_diacritics_and_mon_prefix():
    assert _fold("Món Việt") == "viet"
    assert _fold("Trà Sữa") == "tra sua"
    assert _fold(None) == ""
    assert _fold("Món Chay") == "chay"


def test_none_or_empty_profile_scores_zero():
    assert profile_score(_merchant("Phở"), None, CFG) == 0.0
    empty = UserProfilePublic(user_id="u")
    assert profile_score(_merchant("Phở"), empty, CFG) == 0.0


def test_budget_match_boosts_mismatch_zero():
    p = UserProfilePublic(user_id="u", budget_level="student")
    assert profile_score(_merchant("Cơm", price_level="rẻ"), p, CFG) > 0.0
    assert profile_score(_merchant("Sushi", price_level="cao cấp"), p, CFG) == 0.0


def test_budget_en_to_vi_mapping_all_three():
    assert profile_score(_merchant("x", price_level="rẻ"),
                         UserProfilePublic(user_id="u", budget_level="student"), CFG) > 0
    assert profile_score(_merchant("x", price_level="trung bình"),
                         UserProfilePublic(user_id="u", budget_level="standard"), CFG) > 0
    assert profile_score(_merchant("x", price_level="cao cấp"),
                         UserProfilePublic(user_id="u", budget_level="premium"), CFG) > 0


def test_liked_cuisine_overlap_boosts_and_caps():
    p = UserProfilePublic(user_id="u", liked_cuisines=["việt", "chay", "nhật"])
    # 'Món Việt' folds to 'viet' -> 1 hit
    assert profile_score(_merchant("Món Việt"), p, CFG) > 0.0
    # cap: many hits do not exceed liked_cap * w_liked
    p_many = UserProfilePublic(user_id="u", liked_cuisines=["việt", "món việt"])
    capped = profile_score(_merchant("Món Việt"), p_many, CFG)
    assert capped <= CFG.w_liked * CFG.liked_cap


def test_disliked_cuisine_penalizes():
    p = UserProfilePublic(user_id="u", disliked_cuisines=["thái"])
    assert profile_score(_merchant("Món Thái"), p, CFG) < 0.0
    assert profile_score(_merchant("Phở"), p, CFG) == 0.0


def test_dietary_chay_boost_only_for_veg_signal():
    p = UserProfilePublic(user_id="u", dietary=["ăn chay"])
    assert profile_score(_merchant("Món Chay", taste_tags=["chay"]), p, CFG) > 0.0
    assert profile_score(_merchant("Phở Bò"), p, CFG) == 0.0


def test_signals_stack():
    p = UserProfilePublic(user_id="u", budget_level="student", liked_cuisines=["việt"])
    m = _merchant("Món Việt", price_level="rẻ", taste_tags=["chay"])
    # budget + liked both fire; dietary does NOT (profile has no chay dietary)
    assert profile_score(m, p, CFG) == CFG.w_budget + CFG.w_liked


def test_hard_filter_default_off():
    p = UserProfilePublic(user_id="u", disliked_cuisines=["thái"])
    assert should_hard_filter(_merchant("Món Thái"), p, CFG) is False


def test_hard_filter_when_enabled():
    cfg = RankingConfig(hard_filter_disliked=True)
    p = UserProfilePublic(user_id="u", disliked_cuisines=["thái"])
    assert should_hard_filter(_merchant("Món Thái"), p, cfg) is True
    assert should_hard_filter(_merchant("Phở"), p, cfg) is False
