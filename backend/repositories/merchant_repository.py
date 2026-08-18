"""Merchant repository (C-01) — data access layer for UC-04 search.

Provides CRUD and search operations for merchants, menu items, and reviews.
Optimized: eager-loads ratings + profile to eliminate N+1 query patterns.
"""
from __future__ import annotations

from core.text_norm import fold_diacritics as _norm_text
from datetime import time
from typing import Any

from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import Session, joinedload

from database.models import Merchant, MenuItem, Review, MerchantProfile, MerchantRating, FoodImage
from core.errors import NotFoundError

# Vietnamese diacritic chars → ASCII base (paired char-by-char for SQL translate()).
# Lets ilike match across diacritics: "pho" ≡ "phở", "com" ≡ "cơm", "ha noi" ≡ "Hà Nội".
_VN_DIACRITICS = (
    "àáảãạăắằẳẵặâấầẩẫậ"      # 17 → a
    "èéẻẽẹêếềểễệ"            # 11 → e
    "ìíỉĩị"                  # 5  → i
    "òóỏõọôốồổỗộơớờởỡợ"      # 17 → o
    "ùúủũụưứừửữự"            # 11 → u
    "ỳýỷỹỵ"                  # 5  → y
    "đ"                      # 1  → d
)
_VN_ASCII = "a" * 17 + "e" * 11 + "i" * 5 + "o" * 17 + "u" * 11 + "y" * 5 + "d"


# `_norm_text` is imported above from core.text_norm (audit #15). It MUST agree with the
# SQL-side _norm_col translate() below so a no-diacritic query ("pho") matches "phở".


def _norm_col(column: Any) -> Any:
    """SQL expression: lowercase the column and strip Vietnamese diacritics via translate()."""
    return func.translate(func.lower(column), _VN_DIACRITICS, _VN_ASCII)


def _parse_time(value: Any) -> time | None:
    """Parse a 'HH:MM[:SS]' string (or time) into datetime.time, else None."""
    if value is None or isinstance(value, time):
        return value
    try:
        return time.fromisoformat(str(value))
    except ValueError:
        return None


class MerchantRepository:
    """Repository for merchant data access with search capabilities."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, merchant_id: str) -> Merchant | None:
        """Fetch merchant by ID."""
        return self._db.get(Merchant, merchant_id)

    def get_by_ids(self, merchant_ids: list[str]) -> list[Merchant]:
        """Batch-fetch merchants by ID (one query). Missing ids are simply absent
        from the result — callers match by merchant_id."""
        if not merchant_ids:
            return []
        return list(self._db.query(Merchant).filter(Merchant.merchant_id.in_(merchant_ids)).all())

    def get_by_id_or_raise(self, merchant_id: str) -> Merchant:
        """Fetch merchant by ID or raise NotFoundError."""
        merchant = self.get_by_id(merchant_id)
        if merchant is None:
            raise NotFoundError(
                f"Không tìm thấy merchant '{merchant_id}'.",
                details={"merchant_id": merchant_id},
            )
        return merchant

    def search_merchants(
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
        offset: int = 0,
    ) -> list[Merchant]:
        """Search merchants with filters (§11.2 UC-04).

        Eager-loads `ratings` and `profile` so callers can access them without
        extra DB round-trips (eliminates N+1).

        Supports:
        - Full-text search (name + cuisine + menu items)
        - Cuisine, city filters
        - Price range (from menu items)
        - Rating filter (from platform ratings)
        - Geo-spatial search (lat/lng + radius via service layer)
        """
        stmt = select(Merchant).options(
            joinedload(Merchant.ratings),
            joinedload(Merchant.profile),
        )

        conditions = []

        if query:
            # Free-text search across merchant name, cuisine, AND menu-item names.
            # Diacritics-insensitive: normalize both sides so "pho" matches "phở".
            escaped_query = _norm_text(query).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query_pattern = f"%{escaped_query}%"
            menu_match = (
                select(MenuItem.item_id)
                .where(
                    MenuItem.merchant_id == Merchant.merchant_id,
                    _norm_col(MenuItem.name).ilike(query_pattern, escape="\\"),
                )
                .exists()
            )
            conditions.append(
                or_(
                    _norm_col(Merchant.name).ilike(query_pattern, escape="\\"),
                    _norm_col(Merchant.cuisine).ilike(query_pattern, escape="\\"),
                    menu_match,
                )
            )

        if cuisine:
            conditions.append(_norm_col(Merchant.cuisine).ilike(f"%{_norm_text(cuisine)}%"))

        if city:
            # Match either the city field OR the address containing the term (districts like
            # "Cầu Giấy" live in address). Diacritics-insensitive ("ha noi" ≡ "Hà Nội").
            escaped_city = _norm_text(city).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            city_pattern = f"%{escaped_city}%"
            conditions.append(
                or_(
                    _norm_col(Merchant.city).ilike(city_pattern, escape="\\"),
                    _norm_col(Merchant.address).ilike(city_pattern, escape="\\"),
                )
            )

        if min_price is not None or max_price is not None:
            price_conditions = [MenuItem.merchant_id == Merchant.merchant_id]
            if min_price is not None:
                price_conditions.append(MenuItem.price >= min_price)
            if max_price is not None:
                price_conditions.append(MenuItem.price <= max_price)
            price_match = select(MenuItem.item_id).where(and_(*price_conditions)).exists()
            conditions.append(price_match)

        if min_rating is not None:
            # Filter by platform rating (ShopeeFood 0..5 scale) — NOT review average.
            conditions.append(
                select(MerchantRating.merchant_id)
                .where(
                    MerchantRating.merchant_id == Merchant.merchant_id,
                    MerchantRating.shopeefood_rating >= min_rating,
                )
                .exists()
            )

        if conditions:
            stmt = stmt.where(and_(*conditions))

        stmt = stmt.distinct().order_by(Merchant.name).limit(limit).offset(offset)
        result = self._db.execute(stmt).unique().scalars().all()
        return list(result)

    def get_menu_items(self, merchant_id: str) -> list[MenuItem]:
        """Fetch all menu items for a merchant."""
        stmt = select(MenuItem).where(MenuItem.merchant_id == merchant_id)
        return list(self._db.execute(stmt).scalars().all())

    def get_top_menu_items(self, merchant_id: str, limit: int = 3) -> list[MenuItem]:
        """Fetch top menu items by popularity (total_like) for a merchant."""
        stmt = (
            select(MenuItem)
            .where(MenuItem.merchant_id == merchant_id)
            .order_by(MenuItem.total_like.desc())
            .limit(limit)
        )
        return list(self._db.execute(stmt).scalars().all())

    def get_top_menu_items_batch(
        self, merchant_ids: list[str], per_merchant: int = 3
    ) -> dict[str, list[MenuItem]]:
        """Batch-fetch top menu items for multiple merchants in one query.

        Uses a window function to rank items per merchant, then filters.
        Returns {merchant_id: [items]}."""
        if not merchant_ids:
            return {}
        rank_col = func.row_number().over(
            partition_by=MenuItem.merchant_id,
            order_by=MenuItem.total_like.desc(),
        ).label("rn")
        sub = (
            select(MenuItem, rank_col)
            .where(MenuItem.merchant_id.in_(merchant_ids))
            .subquery()
        )
        stmt = select(MenuItem).join(sub, MenuItem.item_id == sub.c.item_id).where(sub.c.rn <= per_merchant)
        items = list(self._db.execute(stmt).scalars().all())
        result: dict[str, list[MenuItem]] = {mid: [] for mid in merchant_ids}
        for item in items:
            result.setdefault(item.merchant_id, []).append(item)
        return result

    def get_representative_images(
        self, merchant_ids: list[str]
    ) -> dict[str, str]:
        """Batch-fetch ONE representative food image per merchant (best dish_image_quality).

        Real merchant-provided photos (ShopeeFood CDN) shown on result cards. Ranks each
        merchant's food_images by dish_image_quality DESC NULLS LAST (quality score is
        usually NULL for scraped rows → falls back to any image), takes the top row.
        Returns {merchant_id: url}; merchants with no image are simply absent."""
        if not merchant_ids:
            return {}
        # rank images per merchant; NULL quality sorts last so a real photo wins over none.
        rank_col = func.row_number().over(
            partition_by=FoodImage.merchant_id,
            order_by=[
                FoodImage.dish_image_quality.desc().nullslast(),
                FoodImage.created_at.desc().nullslast(),
            ],
        ).label("rn")
        sub = (
            select(FoodImage.image_id, FoodImage.merchant_id, FoodImage.url, rank_col)
            .where(FoodImage.merchant_id.in_(merchant_ids))
            .subquery()
        )
        stmt = select(sub.c.merchant_id, sub.c.url).where(sub.c.rn == 1)
        return {mid: url for mid, url in self._db.execute(stmt).all()}

    def get_reviews(self, merchant_id: str, limit: int = 10) -> list[Review]:
        """Fetch recent reviews for a merchant."""
        stmt = (
            select(Review)
            .where(Review.merchant_id == merchant_id)
            .order_by(Review.created_at.desc())
            .limit(limit)
        )
        return list(self._db.execute(stmt).scalars().all())

    def get_platform_rating(self, merchant_id: str) -> float | None:
        """Get authoritative platform rating (ShopeeFood or Foody).

        Prefers ShopeeFood (0..5); falls back to Foody (0..10, scaled to 0..5).
        Uses the eagerly-loaded relationship when available."""
        merchant = self._db.get(Merchant, merchant_id)
        if merchant and merchant.ratings:
            r = merchant.ratings
            if r.shopeefood_rating is not None:
                return float(r.shopeefood_rating)
            if r.foody_rating is not None:
                return round(float(r.foody_rating) / 2, 2)  # normalize 10→5
        return None

    def create_merchant(
        self,
        merchant_id: str,
        name: str,
        cuisine: str,
        city: str,
        address: str | None = None,
        lat: float | None = None,
        lng: float | None = None,
        open_hours: dict[str, Any] | None = None,
    ) -> Merchant:
        """Create a new merchant.

        `open_hours` ({"open", "close"}) is accepted for backward compatibility and
        decomposed into the typed `opens_at` / `closes_at` columns (the legacy JSON
        `open_hours` column was dropped in migration c2d3e4f5a6b7)."""
        opens_at = closes_at = None
        if open_hours:
            opens_at = _parse_time(open_hours.get("open"))
            closes_at = _parse_time(open_hours.get("close"))
        merchant = Merchant(
            merchant_id=merchant_id,
            name=name,
            cuisine=cuisine,
            city=city,
            city_slug=city.lower().replace(" ", "-"),
            address=address,
            lat=lat,
            lng=lng,
            opens_at=opens_at,
            closes_at=closes_at,
        )
        self._db.add(merchant)
        self._db.commit()
        self._db.refresh(merchant)
        return merchant

    def list_cities(self) -> list[str]:
        """Get list of cities with merchants."""
        stmt = select(Merchant.city).distinct().order_by(Merchant.city)
        return list(self._db.execute(stmt).scalars().all())

    def list_cuisines(self) -> list[str]:
        """Get list of available cuisines."""
        stmt = select(Merchant.cuisine).distinct().order_by(Merchant.cuisine)
        return list(self._db.execute(stmt).scalars().all())
