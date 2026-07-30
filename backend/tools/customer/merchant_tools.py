"""Customer tools (F-02) — merchant_search + nearby_merchant.

Phase 0b: basic tools for UC-04 slice.
These tools integrate with tool registry and are consumed by customer agents.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from database.connection import SessionLocal
from repositories.merchant_repository import MerchantRepository
from services.merchant_search_service import MerchantSearchService
from tools.allow_list import agents_allowed_for
from tools.registry import ToolRegistry, ToolSpec


# --------------------------------------------------------------------------- #
# args schemas (explicit → CrewAI adapter surfaces rich field descriptions to
# the LLM, and `list[str]` is typed correctly — the loose `input_schema`
# derivation only knows str/int/float/bool, so it would mistype a list).
# --------------------------------------------------------------------------- #
class MerchantSearchArgs(BaseModel):
    query: str | None = Field(None, description="Từ khoá tự do — tên món/quán ('phở', 'cơm tấm').")
    cuisine: str | None = Field(None, description="Danh mục ẩm thực RỘNG ('Món Việt', 'Nhật'), KHÔNG dùng tên món.")
    city: str | None = Field(None, description="Lọc theo thành phố.")
    min_price: int | None = Field(None, description="Giá tối thiểu.")
    max_price: int | None = Field(None, description="Giá tối đa.")
    min_rating: float | None = Field(None, description="Đánh giá trung bình tối thiểu.")
    lat: float | None = Field(None, description="Vĩ độ người dùng (tìm theo vị trí).")
    lng: float | None = Field(None, description="Kinh độ người dùng (tìm theo vị trí).")
    radius_km: float | None = Field(None, description="Bán kính tối đa (km).")
    limit: int | None = Field(None, description="Số kết quả tối đa.")
    exclude_merchant_ids: list[str] | None = Field(
        None,
        description="Danh sách merchant_id cần LOẠI khỏi kết quả (đã gợi ý ở phiên trước — "
        "phục vụ 'còn quán nào khác'). None/[] = không loại.",
    )


class NearbyMerchantSearchArgs(BaseModel):
    # lat/lng kept optional (None default): the spec's required_args guard returns the friendly
    # Vietnamese nudge, instead of a generic pydantic error, when the LLM omits coordinates.
    lat: float | None = Field(None, description="Vĩ độ vị trí tìm kiếm.")
    lng: float | None = Field(None, description="Kinh độ vị trí tìm kiếm.")
    radius_km: float | None = Field(None, description="Bán kính tìm kiếm (km).")
    query: str | None = Field(None, description="Từ khoá món/tên quán ('phở', 'bún bò').")
    cuisine: str | None = Field(None, description="Danh mục ẩm thực RỘNG, không dùng tên món.")
    limit: int | None = Field(None, description="Số kết quả tối đa.")
    exclude_merchant_ids: list[str] | None = Field(
        None,
        description="Danh sách merchant_id cần LOẠI khỏi kết quả (đã gợi ý ở phiên trước — "
        "phục vụ 'còn quán nào khác'). None/[] = không loại.",
    )


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
    exclude_merchant_ids: list[str] | None = None,
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
        exclude_merchant_ids: Merchant ids to DROP from results (e.g. already-suggested
            in a prior turn, for "còn quán nào khác"). None/[] = no change (subtractive).

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
            exclude_merchant_ids=exclude_merchant_ids,
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
                "excluded_count": len(exclude_merchant_ids) if exclude_merchant_ids else 0,
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
    exclude_merchant_ids: list[str] | None = None,
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
        exclude_merchant_ids: Merchant ids to DROP from results (e.g. already-suggested
            in a prior turn, for "còn quán nào khác"). None/[] = no change (subtractive).

    Returns:
        Nearby merchants sorted by distance
    """
    db = SessionLocal()
    try:
        repo = MerchantRepository(db)
        service = MerchantSearchService(repo)

        results = service.nearby_search(
            lat=lat, lng=lng, radius_km=radius_km, query=query, cuisine=cuisine, limit=limit,
            exclude_merchant_ids=exclude_merchant_ids,
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
                "Pass `exclude_merchant_ids` to drop already-suggested merchants "
                "('còn quán nào khác'). Returns a ranked list."
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
                "exclude_merchant_ids": "list[str] | None",
            },
            output_schema={
                "merchants": "list[dict]",
                "total": "int",
                "filters_applied": "dict",
            },
            allowed_agents=agents_allowed_for("merchant_search"),
            cache_policy="none",  # Search results are dynamic
            source_kind="real",
            args_schema=MerchantSearchArgs,
        ),
        merchant_search,
    )

    reg.register(
        ToolSpec(
            name="nearby_merchant_search",
            description=(
                "Find merchants near a location (Haversine distance). Put a DISH/name "
                "keyword ('phở', 'bún bò') in `query`; use `cuisine` only for a broad "
                "category. Pass `exclude_merchant_ids` to drop already-suggested merchants "
                "('còn quán nào khác'). Used for geo-filter and competitor analysis."
            ),
            input_schema={
                "lat": "float",
                "lng": "float",
                "radius_km": "float | None",
                "query": "str | None",
                "cuisine": "str | None",
                "limit": "int | None",
                "exclude_merchant_ids": "list[str] | None",
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
            args_schema=NearbyMerchantSearchArgs,
        ),
        nearby_merchant_search,
    )
