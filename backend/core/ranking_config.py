"""Profile-based ranking config (phase-02). Additive weights/flags; defaults conservative.

When ``enabled`` AND a profile is present, ``MerchantSearchService`` adds a small
``profile_score`` to ``match_score`` and (optionally) hard-filters. No profile → no effect
(behavior unchanged vs baseline). Weights are deliberately small so ranking nudges rather
than dominates the existing relevance scoring (docs/scoring-methodology.md)."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from core.settings import get_settings


@dataclass(frozen=True)
class RankingConfig:
    enabled: bool = True
    w_budget: float = 0.06
    w_liked: float = 0.03
    liked_cap: int = 2
    w_disliked: float = 0.05
    w_dietary: float = 0.04
    w_liked_merchant: float = 0.06  # episodic (phase-05): a directly-liked merchant — explicit > cuisine
    hard_filter_disliked: bool = False


@lru_cache
def get_ranking_config() -> RankingConfig:
    """Build the ranking config from settings (cached per process; flip via env to kill-switch)."""
    s = get_settings()
    return RankingConfig(
        enabled=s.ranking_enabled,
        w_budget=s.ranking_w_budget,
        w_liked=s.ranking_w_liked,
        liked_cap=s.ranking_liked_cap,
        w_disliked=s.ranking_w_disliked,
        w_dietary=s.ranking_w_dietary,
        # Episodic weight is optional in settings (getattr default keeps it out of settings.py).
        w_liked_merchant=getattr(s, "ranking_w_liked_merchant", 0.06),
        hard_filter_disliked=s.ranking_hard_filter_disliked,
    )
