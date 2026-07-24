"""Merchant repository (C-01) — data access layer for UC-04 search.

Provides CRUD and search operations for merchants, menu items, and reviews.
Phase 0b: basic query + geo search foundation for UC-04 slice.
"""
from __future__ import annotations

from datetime import datetime, time
from typing import Any

from sqlalchemy import select, and_, or_, exists
from sqlalchemy.orm import Session

from database.models import Merchant, MenuItem, Review
from core.errors import NotFoundError


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

        Supports:
        - Full-text search (name + description)
        - Cuisine, city filters
        - Price range (from menu items)
        - Rating filter (from reviews)
        - Geo-spatial search (lat/lng + radius)
        """
        stmt = select(Merchant)

        # Build filters
        conditions = []

        if query:
            # Free-text search across merchant name, cuisine, AND menu-item names, so a
            # DISH keyword ("phở", "cơm tấm", "trà sữa") finds merchants that sell it even
            # when their cuisine column is a broad category ("Món Việt"). The menu match
            # is a correlated EXISTS to avoid row duplication.
            # Escape LIKE special chars (backslash first) to prevent injection.
            escaped_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query_pattern = f"%{escaped_query}%"
            menu_match = (
                select(MenuItem.item_id)
                .where(
                    MenuItem.merchant_id == Merchant.merchant_id,
                    MenuItem.name.ilike(query_pattern, escape="\\"),
                )
                .exists()
            )
            conditions.append(
                or_(
                    Merchant.name.ilike(query_pattern, escape="\\"),
                    Merchant.cuisine.ilike(query_pattern, escape="\\"),
                    menu_match,
                )
            )

        if cuisine:
            conditions.append(Merchant.cuisine == cuisine)

        if city:
            conditions.append(Merchant.city == city)

        if min_price is not None or max_price is not None:
            # Join with menu items for price filtering
            stmt = stmt.outerjoin(MenuItem)
            if min_price is not None:
                conditions.append(MenuItem.price >= min_price)
            if max_price is not None:
                conditions.append(MenuItem.price <= max_price)

        if min_rating is not None:
            # Join with reviews for rating filtering
            stmt = stmt.outerjoin(Review)
            conditions.append(Review.rating >= min_rating)

        if conditions:
            stmt = stmt.where(and_(*conditions))

        # Geo-spatial filtering (Haversine applied in service layer for now)
        # TODO: Add native Haversine function to PostgreSQL in Phase 1

        stmt = stmt.distinct().order_by(Merchant.name).limit(limit).offset(offset)
        result = self._db.execute(stmt).scalars().all()
        return list(result)

    def get_menu_items(self, merchant_id: str) -> list[MenuItem]:
        """Fetch all menu items for a merchant."""
        stmt = select(MenuItem).where(MenuItem.merchant_id == merchant_id)
        return list(self._db.execute(stmt).scalars().all())

    def get_reviews(self, merchant_id: str, limit: int = 10) -> list[Review]:
        """Fetch recent reviews for a merchant."""
        stmt = (
            select(Review)
            .where(Review.merchant_id == merchant_id)
            .order_by(Review.created_at.desc())
            .limit(limit)
        )
        return list(self._db.execute(stmt).scalars().all())

    def get_avg_rating(self, merchant_id: str) -> float | None:
        """Calculate average rating for a merchant."""
        stmt = select(Review.rating).where(
            Review.merchant_id == merchant_id, Review.rating.is_not(None)
        )
        ratings = list(self._db.execute(stmt).scalars().all())
        if not ratings:
            return None
        return sum(ratings) / len(ratings)

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
