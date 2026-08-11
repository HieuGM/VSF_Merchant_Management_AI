"""Merchant search service (C-04) — ranking + candidate generation (§11.2).

Optimized: uses eagerly-loaded ratings/profile from repository (no N+1),
enriched SearchResult with profile data, improved match scoring with
distance decay, dimension scores, tag overlap, and menu-item match tracking.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from core.profile_context import get_current_profile
from core.query_relevance import query_relevance
from core.ranking_config import get_ranking_config
from database.models import Merchant, MenuItem
from models.preference import UserProfilePublic
from repositories.merchant_repository import MerchantRepository, _norm_text
from services.profile_ranking import profile_score, should_hard_filter


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate Haversine distance between two coordinates in kilometers."""
    R = 6371.0
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def _nearby_match_score(merchant: Merchant, query: str | None) -> float:
    """Graded query relevance (name > cuisine > menu) for nearby ranking. 0 when no query → ranks
    purely by distance. Tone-aware (a 'phở' query no longer rides on 'Phố Cổ' in a name). Replaces
    the old 3-step 1.0/0.7/0.4 which capped everything at 1.0 and gave no differentiation."""
    if not query:
        return 0.0
    return query_relevance(
        query, merchant.name, merchant.cuisine, getattr(merchant, "taste_tags", None)
    )


@dataclass
class SearchResult:
    """Ranked merchant result with enriched metadata for agent consumption."""

    merchant: Merchant
    distance_km: float | None = None
    avg_rating: float | None = None
    match_score: float = 0.0
    # Enrichment fields (from eagerly-loaded relationships)
    tier: str | None = None
    price_level: str | None = None
    overall_score: float | None = None
    top_menu_items: list[dict[str, Any]] = field(default_factory=list)
    representative_image: str | None = None  # real merchant food photo (ShopeeFood CDN)
    _matched_via_menu: bool = False  # internal flag for scoring

    def to_dict(self) -> dict[str, Any]:
        """Convert to API/agent response format — enriched with profile data."""
        d: dict[str, Any] = {
            "merchant_id": self.merchant.merchant_id,
            "name": self.merchant.name,
            "cuisine": self.merchant.cuisine,
            "address": self.merchant.address,
            "city": self.merchant.city,
            "distance_km": round(self.distance_km, 2) if self.distance_km else None,
            "avg_rating": self.avg_rating,
            "match_score": round(self.match_score, 3),
            # Enrichment fields — agent can reason about these directly
            "tier": self.tier,
            "price_level": self.price_level,
            "taste_tags": list(self.merchant.taste_tags or []),
            "image_url": self.representative_image,
        }
        if self.top_menu_items:
            d["top_dishes"] = self.top_menu_items
        return d


class MerchantSearchService:
    """Service for merchant search with ranking logic."""

    def __init__(self, repository: MerchantRepository) -> None:
        self._repo = repository

    def search(
        self,
        *,
        query: str | None = None,
        cuisine: str | None = None,
        city: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        min_rating: float | None = None,
        lat: float | None = None,
        lng: float | None = None,
        radius_km: float | None = None,
        limit: int = 20,
        exclude_merchant_ids: list[str] | None = None,
        profile: UserProfilePublic | None = None,
    ) -> list[SearchResult]:
        """Search merchants with filters and ranking (UC-04).

        Uses eagerly-loaded ratings/profile from repository — no N+1 queries.
        """
        # Truth-first guard: with NO discriminative signal (no query/cuisine/city, no geo, AND no
        # rating/price constraint), return [] instead of dumping the whole catalog ordered by
        # name. That catalog-by-name fallthrough (the repo has no WHERE clause when conditions=[])
        # is what surfaced 3 irrelevant Huế/HCM merchants for a fictional "Sao Hỏa" query (TC-16).
        # min_rating/min_price/max_price count as discriminative so constraint-only queries like
        # "chỉ lấy quán đúng 5.0 sao" (TC-14) still search instead of being emptied out.
        if (
            not (query or cuisine or city)
            and lat is None and lng is None
            and min_rating is None and min_price is None and max_price is None
        ):
            return []

        # phase-02: taste profile (explicit arg, else request ContextVar set by the flow
        # around crew.kickoff) + ranking config. No profile -> ranking is a no-op.
        profile = profile if profile is not None else get_current_profile()
        cfg = get_ranking_config()
        ranking_on = cfg.enabled and profile is not None

        merchants = self._repo.search_merchants(
            query=query, cuisine=cuisine, city=city,
            min_price=min_price, max_price=max_price,
            min_rating=min_rating,
            limit=limit * 2,
        )

        # Subtractive exclude: drop ids BEFORE ranking/distance scoring so excluded
        # merchants never win ties or consume a limit slot. None/[] = no change.
        if exclude_merchant_ids:
            excluded = set(exclude_merchant_ids)
            merchants = [m for m in merchants if m.merchant_id not in excluded]

        results: list[SearchResult] = []

        for merchant in merchants:
            distance_km = None
            if lat is not None and lng is not None:
                if merchant.lat is not None and merchant.lng is not None:
                    distance_km = haversine_distance(lat, lng, merchant.lat, merchant.lng)

            if radius_km is not None and distance_km is not None:
                if distance_km > radius_km:
                    continue

            # Extract from eagerly-loaded relationships (no extra query)
            avg_rating = _platform_rating(merchant)
            tier = merchant.profile.tier if merchant.profile else None
            price_level = merchant.profile.price_level if merchant.profile else None
            overall = None
            if merchant.profile and merchant.profile.overall_score_internal is not None:
                overall = float(merchant.profile.overall_score_internal)

            # Track whether query matched via menu item (for scoring)
            matched_via_menu = False
            if query and query.lower() not in (merchant.name or "").lower() \
                    and query.lower() not in (merchant.cuisine or "").lower():
                matched_via_menu = True  # must have matched via EXISTS menu subquery

            match_score = self._calculate_match_score(
                merchant, query, cuisine, city, avg_rating,
                distance_km=distance_km,
                overall_score=overall,
                matched_via_menu=matched_via_menu,
            )
            if ranking_on:  # phase-02: taste-profile boost + optional hard-filter
                if should_hard_filter(merchant, profile, cfg):
                    continue
                match_score += profile_score(merchant, profile, cfg)

            results.append(
                SearchResult(
                    merchant=merchant,
                    distance_km=distance_km,
                    avg_rating=avg_rating,
                    match_score=match_score,
                    tier=tier,
                    price_level=price_level,
                    overall_score=overall,
                    _matched_via_menu=matched_via_menu,
                )
            )

        results.sort(
            key=lambda r: (
                -r.match_score,
                r.distance_km if r.distance_km is not None else 9999,
            )
        )

        final = results[:limit]

        # Batch-load top menu items for the final set (1 query total instead of N)
        if final:
            mids = [r.merchant.merchant_id for r in final]
            top_items = self._repo.get_top_menu_items_batch(mids, per_merchant=3)
            images = self._repo.get_representative_images(mids)
            for r in final:
                items = top_items.get(r.merchant.merchant_id, [])
                r.top_menu_items = [
                    {"name": it.name, "price": it.price, "likes": it.total_like}
                    for it in items
                ]
                r.representative_image = images.get(r.merchant.merchant_id)

        return final

    def nearby_search(
        self,
        lat: float,
        lng: float,
        radius_km: float = 5.0,
        cuisine: str | None = None,
        query: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        min_rating: float | None = None,
        limit: int = 20,
        exclude_merchant_ids: list[str] | None = None,
        profile: UserProfilePublic | None = None,
    ) -> list[SearchResult]:
        """Find merchants near a location (Haversine-based).

        Fetches a wide candidate pool (whole catalog) so the geo filter isn't thwarted by a
        text-relevance cutoff — otherwise nearby returns 0 even when matching merchants exist
        near the user (they were just beyond the limit). Auto-expands the radius when the result
        is sparse: desktop IP geolocation can be off by kilometres and some districts have few
        merchants, so a hard 5km cutoff would wrongly return nothing.

        `min_price`/`max_price`/`min_rating` are HARD filters (forwarded to search_merchants,
        which enforces them via EXISTS subqueries on menu prices / platform rating) — geo
        queries must respect explicit price/rating constraints instead of silently dropping
        them and surfacing the nearest merchants regardless."""
        # phase-02: taste profile (explicit arg, else request ContextVar) + ranking config.
        profile = profile if profile is not None else get_current_profile()
        cfg = get_ranking_config()
        ranking_on = cfg.enabled and profile is not None

        # 2000 > catalog size (~1681) → every query/cuisine/price/rating-matching merchant is
        # a geo candidate. Constraints are applied HERE so radius-widening below never relaxes
        # them (the candidate pool is already filtered before geo_filter runs).
        candidates = self._repo.search_merchants(
            query=query, cuisine=cuisine,
            min_price=min_price, max_price=max_price, min_rating=min_rating,
            limit=2000,
        )

        # Subtractive exclude: drop ids BEFORE geo/ranking so excluded merchants never win ties
        # or consume a limit slot. None/[] = no change.
        if exclude_merchant_ids:
            excluded = set(exclude_merchant_ids)
            candidates = [m for m in candidates if m.merchant_id not in excluded]

        def geo_filter(radius: float) -> list[SearchResult]:
            out: list[SearchResult] = []
            for merchant in candidates:
                if merchant.lat is None or merchant.lng is None:
                    continue
                distance_km = haversine_distance(lat, lng, merchant.lat, merchant.lng)
                if distance_km <= radius:
                    avg_rating = _platform_rating(merchant)
                    tier = merchant.profile.tier if merchant.profile else None
                    price_level = merchant.profile.price_level if merchant.profile else None
                    match_score = _nearby_match_score(merchant, query)
                    if ranking_on:  # phase-02: taste-profile boost + optional hard-filter
                        if should_hard_filter(merchant, profile, cfg):
                            continue
                        match_score += profile_score(merchant, profile, cfg)
                    out.append(
                        SearchResult(
                            merchant=merchant,
                            distance_km=distance_km,
                            avg_rating=avg_rating,
                            match_score=match_score,
                            tier=tier,
                            price_level=price_level,
                        )
                    )
            # Rank by relevance first (name > cuisine > menu-only match), then distance — so a
            # real "trà sữa" shop outranks a Pizza Hut that only matched "tra sua" via menu items.
            out.sort(key=lambda r: (-r.match_score, r.distance_km or 9999))
            return out

        results = geo_filter(radius_km)
        # Sparse-safety: escalate the radius modestly until we have a few results. Capped at
        # 20km — beyond that, results aren't meaningfully "nearby" for a "gần đây" query and an
        # honest empty result (→ friendly "nothing close by" answer) is better than a 50km
        # suggestion. (The search agent is instructed NOT to drop these nearest results, so the
        # answer can state the real distance instead of returning nothing.)
        if len(results) < 3:
            for wider in (10.0, 20.0):
                if wider <= radius_km:
                    continue
                wider_results = geo_filter(wider)
                if wider_results:
                    results = wider_results
                    if len(results) >= 3:
                        break
        out = results[:limit]
        if out:
            images = self._repo.get_representative_images(
                [r.merchant.merchant_id for r in out]
            )
            for r in out:
                r.representative_image = images.get(r.merchant.merchant_id)
        return out

    def _calculate_match_score(
        self,
        merchant: Merchant,
        query: str | None,
        cuisine: str | None,
        city: str | None,
        avg_rating: float | None,
        *,
        distance_km: float | None = None,
        overall_score: float | None = None,
        matched_via_menu: bool = False,
    ) -> float:
        """Calculate relevance score (0-1) based on multi-signal matching.

        Scoring (max 1.0):
        - Query match in name:        +0.20
        - Query match in menu items:  +0.15  (weaker than name but still relevant)
        - Cuisine match:              +0.20
        - City match:                 +0.10
        - Platform rating (4+/5):     +0.10
        - Overall dimension score:    +0.15  (scaled: score * 0.15)
        - Distance bonus (<2km):      +0.10  (decays linearly to 0 at 10km)
        """
        score = 0.0

        # Query relevance (name > cuisine > menu, tone-aware) is the PRIMARY driver (~70%). The
        # old scorer gave a name match (+0.20) barely more than a menu match (+0.15) and let
        # constant signals dominate → a chicken place with phở on the menu ranked ~equal to a real
        # phở shop. Now a name match scores well above a menu-only hit.
        rel = query_relevance(
            query, merchant.name, merchant.cuisine,
            getattr(merchant, "taste_tags", None), matched_via_menu,
        )
        score += rel * 0.70

        # `cuisine` is the explicit cuisine FILTER (already enforced by the repo) → constant across
        # the filtered set, so it is not re-scored here.

        # City match (small tiebreaker)
        if city and (merchant.city or "").lower() == city.lower():
            score += 0.05

        # Platform rating bonus
        if avg_rating is not None and avg_rating >= 4.0:
            score += 0.05

        # Overall dimension score contribution
        if overall_score is not None:
            score += overall_score * 0.10

        # Distance bonus (closer = better, caps at 2km = full bonus, 0 at 10km+)
        if distance_km is not None and distance_km < 10:
            score += max(0.0, 0.10 * (1.0 - distance_km / 10.0))

        return min(score, 1.0)


def _platform_rating(merchant: Merchant) -> float | None:
    """Extract platform rating from eagerly-loaded relationship (no extra query).

    Prefers ShopeeFood (0..5); falls back to Foody (0..10, scaled to 0..5)."""
    r = merchant.ratings
    if r is None:
        return None
    if r.shopeefood_rating is not None:
        return float(r.shopeefood_rating)
    if r.foody_rating is not None:
        return round(float(r.foody_rating) / 2, 2)
    return None
