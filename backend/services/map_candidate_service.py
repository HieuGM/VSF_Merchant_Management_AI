"""Build policy-filtered GeoJSON from the H3 retrieval candidate set."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy.orm import Session

from core.errors import InsufficientDataError
from database.models import Merchant
from repositories.merchant_repository import MerchantRepository
from services.merchant_data_policy import MerchantDataPolicy


class MapCandidateService:
    """Project an owner and retrieved public candidates into GeoJSON features."""

    def __init__(self, db: Session) -> None:
        self._repository = MerchantRepository(db)

    def merchant_feature(self, merchant: Merchant, role: str) -> dict[str, Any]:
        public = MerchantDataPolicy(merchant.merchant_id).competitor_public(
            {
                "merchant_id": merchant.merchant_id,
                "name": merchant.name,
                "cuisine": merchant.cuisine,
                "category": merchant.category,
                "city": merchant.city,
                "city_slug": merchant.city_slug,
                "address": merchant.address,
                "lat": merchant.lat,
                "lng": merchant.lng,
                "is_active": merchant.is_active,
            }
        )
        public["role"] = role
        return {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [merchant.lng, merchant.lat],
            },
            "properties": public,
        }

    def build_feature_collection(
        self,
        *,
        merchant_id: str,
        user_lat: float | None,
        user_lng: float | None,
        radius_km: float,
        candidate_merchant_ids: Iterable[str] = (),
        recommended_merchant_ids: Iterable[str] = (),
    ) -> dict[str, Any]:
        owner = self._repository.get_by_id(merchant_id)
        if owner is None:
            # Coordinates for demo merchants across TP. HCM, Hà Nội, Đà Nẵng
            DEMO_COORDS: dict[str, tuple[float, float, str, str]] = {
                '94': (10.7715, 106.6984, "Green Life Poke", "TP. Hồ Chí Minh"),
                '102': (10.7780, 106.7020, "Bếp Việt Delicacy", "TP. Hồ Chí Minh"),
                '145': (21.0180, 105.8520, "Bún Chả Hương Liên", "Hà Nội"),
                '208': (21.0285, 105.8545, "Phở Thìn Bờ Hồ", "Hà Nội"),
                '312': (16.0680, 108.2205, "Mì Quảng Bà Mua", "Đà Nẵng"),
                '420': (10.7730, 106.7050, "Tokyo Sushi & Sashimi Bar", "TP. Hồ Chí Minh"),
            }
            demo_info = DEMO_COORDS.get(str(merchant_id))
            default_lat = demo_info[0] if demo_info else (user_lat or 10.7715 + (int(merchant_id) % 20) * 0.005)
            default_lng = demo_info[1] if demo_info else (user_lng or 106.6984 + (int(merchant_id) % 20) * 0.005)
            default_name = demo_info[2] if demo_info else f"Merchant #{merchant_id}"
            default_city = demo_info[3] if demo_info else "TP. Hồ Chí Minh"

            owner = Merchant(
                merchant_id=merchant_id,
                name=default_name,
                cuisine="F&B Merchant",
                city=default_city,
                city_slug=default_city.lower().replace(" ", "-"),
                address=f"Khu vực {default_city}",
                lat=default_lat,
                lng=default_lng,
                is_active=True,
            )

        if (user_lat is None) != (user_lng is None):
            raise InsufficientDataError("Cần truyền đồng thời lat và lng của người dùng.")

        origin_lat = user_lat if user_lat is not None else owner.lat
        origin_lng = user_lng if user_lng is not None else owner.lng
        if origin_lat is None or origin_lng is None:
            raise InsufficientDataError(
                "Merchant chưa có vị trí; cần cung cấp vị trí người dùng để hiển thị bản đồ."
            )

        recommended_ids = {str(value) for value in recommended_merchant_ids}
        retrieved_ids = {
            str(value)
            for value in candidate_merchant_ids
            if str(value) != owner.merchant_id
        }
        features: list[dict[str, Any]] = []
        if owner.lat is not None and owner.lng is not None:
            features.append(self.merchant_feature(owner, "owner"))
        if user_lat is not None and user_lng is not None:
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [user_lng, user_lat]},
                    "properties": {"role": "user_location"},
                }
            )

        candidates = {
            candidate.merchant_id: candidate
            for candidate in self._repository.find_nearby_candidates(
                lat=origin_lat,
                lng=origin_lng,
                radius_km=radius_km,
                city=owner.city,
                exclude_merchant_id=owner.merchant_id,
                limit=100,
            )
        }
        for candidate in self._repository.get_by_ids(list(retrieved_ids)):
            candidates.setdefault(candidate.merchant_id, candidate)

        for candidate in candidates.values():
            role = (
                "recommended"
                if candidate.merchant_id in recommended_ids
                else "competitor"
                if candidate.cuisine == owner.cuisine
                else "nearby"
            )
            features.append(self.merchant_feature(candidate, role))

        return {"type": "FeatureCollection", "features": features}
