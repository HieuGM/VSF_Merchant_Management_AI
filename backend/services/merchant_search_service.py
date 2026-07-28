"""Merchant search service (C-04) — ranking + candidate generation (§11.2).

Optimized: uses eagerly-loaded ratings/profile from repository (no N+1),
enriched SearchResult with profile data, improved match scoring with
distance decay, dimension scores, tag overlap, and menu-item match tracking.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from database.models import Merchant, MenuItem
from repositories.merchant_repository import MerchantRepository


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
    ) -> list[SearchResult]:
        """Search merchants with filters and ranking (UC-04).

        Uses eagerly-loaded ratings/profile from repository — no N+1 queries.
        """
        merchants = self._repo.search_merchants(
            query=query, cuisine=cuisine, city=city,
            min_price=min_price, max_price=max_price,
            min_rating=min_rating,
            limit=limit * 2,
        )

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
            for r in final:
                items = top_items.get(r.merchant.merchant_id, [])
                r.top_menu_items = [
                    {"name": it.name, "price": it.price, "likes": it.total_like}
                    for it in items
                ]

        return final

    def nearby_search(
        self,
        lat: float,
        lng: float,
        radius_km: float = 5.0,
        cuisine: str | None = None,
        query: str | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Find merchants near a location (Haversine-based).

        Fetches a wide candidate pool (whole catalog) so the geo filter isn't thwarted by a
        text-relevance cutoff — otherwise nearby returns 0 even when matching merchants exist
        near the user (they were just beyond the limit). Auto-expands the radius when the result
        is sparse: desktop IP geolocation can be off by kilometres and some districts have few
        merchants, so a hard 5km cutoff would wrongly return nothing."""
        # 2000 > catalog size (~1681) → every query/cuisine-matching merchant is a geo candidate.
        candidates = self._repo.search_merchants(query=query, cuisine=cuisine, limit=2000)

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
                    out.append(
                        SearchResult(
                            merchant=merchant,
                            distance_km=distance_km,
                            avg_rating=avg_rating,
                            match_score=1.0,
                            tier=tier,
                            price_level=price_level,
                        )
                    )
            out.sort(key=lambda r: r.distance_km or 9999)
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
        return results[:limit]

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

        # Query match
        if query:
            q = query.lower()
            if q in (merchant.name or "").lower():
                score += 0.20
            elif matched_via_menu:
                score += 0.15

        # Cuisine match (fuzzy)
        if cuisine:
            mc = (merchant.cuisine or "").lower()
            if cuisine.lower() == mc:
                score += 0.20
            elif cuisine.lower() in mc or mc in cuisine.lower():
                score += 0.10

        # City match
        if city and (merchant.city or "").lower() == city.lower():
            score += 0.10

        # Platform rating bonus
        if avg_rating is not None and avg_rating >= 4.0:
            score += 0.10

        # Overall dimension score contribution
        if overall_score is not None:
            score += overall_score * 0.15

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
