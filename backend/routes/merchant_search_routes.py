"""Merchant search routes (Dev A) — UC-04 search API with cache integration.

Phase 0b: Replace 501 stub with real implementation + cache candidate.
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Depends
from pydantic import BaseModel, Field

from core.cache import CacheKeys, CachePort
from core.dependencies import get_cache
from core.tracing import new_id


router = APIRouter(prefix="/api/v1/merchants", tags=["merchant-search"])


class MerchantSearchRequest(BaseModel):
    """Search request model."""

    query: str | None = Field(None, description="Text search query")
    cuisine: str | None = Field(None, description="Cuisine filter")
    city: str | None = Field(None, description="City filter")
    budget: str | None = Field(None, description="Budget level: student|standard|premium")
    lat: float | None = Field(None, ge=-90, le=90, description="User latitude (-90 to 90)")
    lng: float | None = Field(None, ge=-180, le=180, description="User longitude (-180 to 180)")
    radius_km: float | None = Field(5.0, gt=0, le=500, description="Search radius in km (max 500)")
    limit: int = Field(20, ge=1, le=100, description="Max results")


class MerchantSearchResponse(BaseModel):
    """Search response model."""

    trace_id: str
    merchants: list[dict]
    total: int
    filters_applied: dict
    cache_status: str  # "hit" | "miss" | "disabled"


@router.get("/search", response_model=MerchantSearchResponse)
def search_merchants(
    query: str | None = Query(None, description="Text search query"),
    cuisine: str | None = Query(None, description="Cuisine filter"),
    city: str | None = Query(None, description="City filter"),
    budget: str | None = Query(None, description="Budget level"),
    lat: float | None = Query(None, ge=-90, le=90, description="User latitude"),
    lng: float | None = Query(None, ge=-180, le=180, description="User longitude"),
    radius_km: float | None = Query(5.0, gt=0, le=500, description="Search radius km"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    cache: CachePort = Depends(get_cache),
) -> MerchantSearchResponse:
    """Search merchants with filters (UC-04).

    Supports:
    - Text search (name, cuisine)
    - Cuisine, city filters
    - Budget level → price range
    - Geo-spatial search (Haversine)
    - Cache integration (Phase 0b: in-memory adapter)

    Returns:
        Ranked merchant list with trace metadata
    """
    # Build cache key
    cache_key = CacheKeys.merchant_search(
        query=query or "",
        cuisine=cuisine or "",
        city=city or "",
        budget=budget or "",
        lat=lat or 0.0,
        lng=lng or 0.0,
        radius_km=radius_km or 0.0,
        limit=limit,
    )

    # Try cache
    cached = cache.get(cache_key)
    if cached:
        return MerchantSearchResponse(
            trace_id=cached["trace_id"],
            merchants=cached["merchants"],
            total=cached["total"],
            filters_applied=cached["filters_applied"],
            cache_status="hit",
        )

    # Execute search directly via the tool (deterministic, no LLM). The CrewAI crew is
    # reserved for the agent-chat endpoint (routes/customer_agent_routes.py).
    from tools.customer.merchant_tools import merchant_search

    budget_ranges = {
        "student": (15000, 50000),
        "standard": (50000, 150000),
        "premium": (150000, None),
    }
    min_price, max_price = budget_ranges.get((budget or "").lower(), (None, None))

    trace_id = new_id("trace")
    result = merchant_search(
        query=query,
        cuisine=cuisine,
        city=city,
        min_price=min_price,
        max_price=max_price,
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        limit=limit,
    )

    # Cache result (TTL: 5 minutes)
    cache.set(
        cache_key,
        {
            "trace_id": trace_id,
            "merchants": result["merchants"],
            "total": result["total"],
            "filters_applied": result["filters_applied"],
        },
        ttl_seconds=300,
    )

    return MerchantSearchResponse(
        trace_id=trace_id,
        merchants=result["merchants"],
        total=result["total"],
        filters_applied=result["filters_applied"],
        cache_status="miss",
    )


@router.get("/nearby")
def nearby_merchants(
    lat: float = Query(..., ge=-90, le=90, description="Latitude (required)"),
    lng: float = Query(..., ge=-180, le=180, description="Longitude (required)"),
    radius_km: float = Query(5.0, gt=0, le=500, description="Search radius km"),
    cuisine: str | None = Query(None, description="Cuisine filter"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    cache: CachePort = Depends(get_cache),
) -> dict:
    """Find merchants near a location (Haversine-based).

    Used by:
    - Customer search (geo-filter)
    - Merchant competitor analysis (UC-03)
    """
    # Build cache key
    cache_key = CacheKeys.nearby_search(
        lat=lat, lng=lng, radius_km=radius_km, cuisine=cuisine or "", limit=limit
    )

    # Try cache
    cached = cache.get(cache_key)
    if cached:
        return {**cached, "cache_status": "hit"}

    # Execute search
    from tools.customer.merchant_tools import nearby_merchant_search

    result = nearby_merchant_search(
        lat=lat, lng=lng, radius_km=radius_km, cuisine=cuisine, limit=limit
    )

    # Cache result (TTL: 2 minutes - location queries change frequently)
    cache.set(cache_key, result, ttl_seconds=120)

    return {**result, "cache_status": "miss"}
