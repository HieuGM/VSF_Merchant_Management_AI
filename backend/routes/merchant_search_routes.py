"""Merchant search + GeoJSON-adjacent search (Dev A). FROZEN paths — design §11.2."""
from __future__ import annotations

from fastapi import APIRouter

from routes.stub_helpers import not_implemented

router = APIRouter(prefix="/api/v1/merchants", tags=["merchant-search"])


@router.get("/search")
def search_merchants() -> object:  # params: q,cuisine,city,min/max_price,min_rating,lat,lng,radius_km,limit
    return not_implemented("GET /api/v1/merchants/search")
