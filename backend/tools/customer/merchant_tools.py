"""Customer tools (F-02) — merchant_search + nearby_merchant.

Phase 0b: basic tools for UC-04 slice.
These tools integrate with tool registry and are consumed by customer agents.
"""
from __future__ import annotations

from typing import Any

from database.connection import SessionLocal
from repositories.merchant_repository import MerchantRepository
from services.merchant_search_service import MerchantSearchService
from tools.allow_list import agents_allowed_for
from tools.registry import ToolRegistry, ToolSpec


def merchant_search(
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
) -> dict[str, Any]:
    """Search for merchants with filters (UC-04).

    Returns ranked list of merchants matching criteria.

    Args:
        query: Free-text keyword — dish/name; matches merchant name, cuisine, and menu items
        cuisine: Filter by BROAD cuisine category only (not a dish name)
        city: Filter by city
        min_price: Minimum price (from menu items)
        max_price: Maximum price (from menu items)
        min_rating: Minimum average rating
        lat: User latitude for geo search
        lng: User longitude for geo search
        radius_km: Maximum distance in km
        limit: Maximum results to return

    Returns:
        Dict with merchants list and metadata
    """
    db = SessionLocal()
    try:
        repo = MerchantRepository(db)
        service = MerchantSearchService(repo)

        results = service.search(
            query=query,
            cuisine=cuisine,
            city=city,
            min_price=min_price,
            max_price=max_price,
            min_rating=min_rating,
            lat=lat,
            lng=lng,
            radius_km=radius_km,
            limit=limit,
        )

        return {
            "merchants": [r.to_dict() for r in results],
            "total": len(results),
            "filters_applied": {
                "query": query,
                "cuisine": cuisine,
                "city": city,
                "price_range": (
                    f"{min_price}-{max_price}" if min_price or max_price else None
                ),
                "min_rating": min_rating,
                "location": ({"lat": lat, "lng": lng, "radius_km": radius_km} if lat else None),
            },
        }
    finally:
        db.close()


def nearby_merchant_search(
    *,
    lat: float,
    lng: float,
    radius_km: float = 5.0,
    query: str | None = None,
    cuisine: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Find merchants near a location using Haversine distance (UC-04, UC-03).

    Used by:
    - Customer restaurant search (geo-filter)
    - Merchant competitor analysis (find nearby competitors)

    Args:
        lat: Latitude coordinate
        lng: Longitude coordinate
        radius_km: Search radius in kilometers
        query: Optional free-text keyword — a DISH or name ("phở", "cơm tấm", "trà sữa").
            Matches merchant name/cuisine/menu. Use this for dish searches, NOT cuisine.
        cuisine: Optional filter for a BROAD cuisine category only (e.g. "Món Việt",
            "Nhật", "Hàn"). Do NOT pass a dish name here.
        limit: Maximum results

    Returns:
        Nearby merchants sorted by distance
    """
    db = SessionLocal()
    try:
        repo = MerchantRepository(db)
        service = MerchantSearchService(repo)

        results = service.nearby_search(
            lat=lat, lng=lng, radius_km=radius_km, query=query, cuisine=cuisine, limit=limit
        )

        return {
            "merchants": [r.to_dict() for r in results],
            "total": len(results),
            "search_center": {"lat": lat, "lng": lng},
            "radius_km": radius_km,
        }
    finally:
        db.close()


def register(reg: ToolRegistry) -> None:
    """Auto-discovery entry point (called by registry.auto_discover)."""
    reg.register(
        ToolSpec(
            name="merchant_search",
            description=(
                "Search merchants by free-text keyword + filters. Put DISH or restaurant "
                "names ('phở', 'cơm tấm', 'trà sữa') in `query` (matches name/cuisine/menu). "
                "Use `cuisine` ONLY for a broad category ('Món Việt', 'Nhật'), never a dish. "
                "Returns a ranked list."
            ),
            input_schema={
                "query": "str | None",
                "cuisine": "str | None",
                "city": "str | None",
                "min_price": "int | None",
                "max_price": "int | None",
                "min_rating": "float | None",
                "lat": "float | None",
                "lng": "float | None",
                "radius_km": "float | None",
                "limit": "int | None",
            },
            output_schema={
                "merchants": "list[dict]",
                "total": "int",
                "filters_applied": "dict",
            },
            allowed_agents=agents_allowed_for("merchant_search"),
            cache_policy="none",  # Search results are dynamic
            source_kind="real",
        ),
        merchant_search,
    )

    reg.register(
        ToolSpec(
            name="nearby_merchant_search",
            description=(
                "Find merchants near a location (Haversine distance). Put a DISH/name "
                "keyword ('phở', 'bún bò') in `query`; use `cuisine` only for a broad "
                "category. Used for geo-filter and competitor analysis."
            ),
            input_schema={
                "lat": "float",
                "lng": "float",
                "radius_km": "float | None",
                "query": "str | None",
                "cuisine": "str | None",
                "limit": "int | None",
            },
            output_schema={
                "merchants": "list[dict]",
                "total": "int",
                "search_center": "dict",
                "radius_km": "float",
            },
            allowed_agents=agents_allowed_for("nearby_merchant_search"),
            cache_policy="none",  # Location-based queries are dynamic
            source_kind="real",
            required_args=("lat", "lng"),  # adapter rejects calls with no coords -> merchant_search instead
        ),
        nearby_merchant_search,
    )
