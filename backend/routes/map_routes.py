"""Map GeoJSON (Dev A). FROZEN path — design §11.8."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database.connection import get_db_session
from services.map_candidate_service import MapCandidateService

router = APIRouter(prefix="/api/v1/maps", tags=["map"])


@router.get("/merchants.geojson")
def merchants_geojson(
    merchant_id: str = Query(..., min_length=1),
    lat: float | None = Query(None, ge=-90, le=90),
    lng: float | None = Query(None, ge=-180, le=180),
    radius_km: float = Query(5.0, gt=0, le=100),
    candidate_merchant_ids: list[str] = Query(default=[]),
    recommended_merchant_ids: list[str] = Query(default=[]),
    db: Session = Depends(get_db_session),
) -> dict[str, object]:
    """Return the owner, user point, and H3-retrieved public candidates as GeoJSON."""
    return MapCandidateService(db).build_feature_collection(
        merchant_id=merchant_id,
        user_lat=lat,
        user_lng=lng,
        radius_km=radius_km,
        candidate_merchant_ids=candidate_merchant_ids,
        recommended_merchant_ids=recommended_merchant_ids,
    )
