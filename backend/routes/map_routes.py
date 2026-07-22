"""Map GeoJSON (Dev A). FROZEN path — design §11.8."""
from __future__ import annotations

from fastapi import APIRouter

from routes.stub_helpers import not_implemented

router = APIRouter(prefix="/api/v1/maps", tags=["map"])


@router.get("/merchants.geojson")
def merchants_geojson() -> object:  # params: lat,lng,radius_km,cuisine,selected_merchant_id
    return not_implemented("GET /api/v1/maps/merchants.geojson")
