"""Merchant tools stub for Customer Discovery Agent (Dev A)."""
from __future__ import annotations
from typing import Any


def nearby_merchant_search(
    lat: float,
    lng: float,
    radius_km: float = 5.0,
    cuisine: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Stub implementation for nearby merchant search."""
    return {
        "merchants": [],
        "total": 0,
        "filters_applied": {
            "lat": lat,
            "lng": lng,
            "radius_km": radius_km,
            "cuisine": cuisine,
        },
    }
