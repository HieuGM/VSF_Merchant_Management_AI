"""Merchant search service (C-04) — ranking + candidate generation (§11.2).

Phase 0b: basic search + Haversine distance for UC-04 slice.
Combines repository queries with business logic for ranking.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from database.models import Merchant
from repositories.merchant_repository import MerchantRepository


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate Haversine distance between two coordinates in kilometers.

    Formula: https://en.wikipedia.org/wiki/Haversine_formula
    """
    R = 6371.0  # Earth radius in km

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))

    return R * c


@dataclass
class SearchResult:
    """Ranked merchant result with metadata."""

    merchant: Merchant
    distance_km: float | None = None
    avg_rating: float | None = None
    match_score: float = 0.0  # Relevance score 0-1

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "merchant_id": self.merchant.merchant_id,
            "name": self.merchant.name,
            "cuisine": self.merchant.cuisine,
            "address": self.merchant.address,
            "city": self.merchant.city,
            "lat": self.merchant.lat,
            "lng": self.merchant.lng,
            "distance_km": round(self.distance_km, 2) if self.distance_km else None,
            "avg_rating": self.avg_rating,
            "match_score": round(self.match_score, 3),
        }


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

        1. Fetch candidates from repository
        2. Calculate distance if location provided
        3. Filter by radius if specified
        4. Calculate relevance score
        5. Sort by relevance + distance
        """
        # Fetch candidates from DB
        merchants = self._repo.search_merchants(
            query=query,
            cuisine=cuisine,
            city=city,
            min_price=min_price,
            max_price=max_price,
            min_rating=min_rating,
            limit=limit * 2,  # Fetch more for post-filtering
        )

        results: list[SearchResult] = []

        for merchant in merchants:
            # Calculate distance if location provided
            distance_km = None
            if lat is not None and lng is not None:
                if merchant.lat is not None and merchant.lng is not None:
                    distance_km = haversine_distance(
                        lat, lng, merchant.lat, merchant.lng
                    )

            # Filter by radius
            if radius_km is not None and distance_km is not None:
                if distance_km > radius_km:
                    continue

            # Get average rating
            avg_rating = self._repo.get_avg_rating(merchant.merchant_id)

            # Calculate relevance score
            match_score = self._calculate_match_score(
                merchant, query, cuisine, city, avg_rating
            )

            results.append(
                SearchResult(
                    merchant=merchant,
                    distance_km=distance_km,
                    avg_rating=avg_rating,
                    match_score=match_score,
                )
            )

        # Sort: relevance first, then distance
        results.sort(
            key=lambda r: (
                -r.match_score,  # Higher relevance first
                r.distance_km if r.distance_km is not None else 9999,  # Closer first
            )
        )

        return results[:limit]

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

        `query` is an optional free-text keyword (dish/name) matched against merchant
        name, cuisine and menu items — so "phở gần đây" filters by the dish, not by an
        exact cuisine label.

        Used by:
        - UC-04 customer search (geo-filter)
        - UC-03 competitor analysis (Dev B's Competitor task)
        """
        # Get candidate merchants (geo filter applied below). Widen the fetch when a
        # keyword filter is present so the radius pass still has enough to work with.
        merchants = self._repo.search_merchants(
            query=query, cuisine=cuisine, limit=limit * 3
        )

        results: list[SearchResult] = []

        for merchant in merchants:
            if merchant.lat is None or merchant.lng is None:
                continue

            distance_km = haversine_distance(lat, lng, merchant.lat, merchant.lng)

            if distance_km <= radius_km:
                avg_rating = self._repo.get_avg_rating(merchant.merchant_id)
                results.append(
                    SearchResult(
                        merchant=merchant,
                        distance_km=distance_km,
                        avg_rating=avg_rating,
                        match_score=1.0,  # Geo match = perfect score
                    )
                )

        # Sort by distance
        results.sort(key=lambda r: r.distance_km or 9999)

        return results[:limit]

    def _calculate_match_score(
        self,
        merchant: Merchant,
        query: str | None,
        cuisine: str | None,
        city: str | None,
        avg_rating: float | None,
    ) -> float:
        """Calculate relevance score (0-1) based on match criteria.

        Scoring:
        - Exact cuisine match: +0.4
        - Exact city match: +0.3
        - Query in name: +0.2
        - High rating (4+): +0.1
        """
        score = 0.0

        # Cuisine match
        if cuisine and merchant.cuisine.lower() == cuisine.lower():
            score += 0.4

        # City match
        if city and merchant.city.lower() == city.lower():
            score += 0.3

        # Query match in name
        if query and query.lower() in merchant.name.lower():
            score += 0.2

        # Rating bonus
        if avg_rating and avg_rating >= 4.0:
            score += 0.1

        return min(score, 1.0)
