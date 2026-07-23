"""Merchant repository (C-01) — data access layer for UC-04 search.

Provides CRUD and search operations for merchants, menu items, and reviews.
Phase 0b: basic query + geo search foundation for UC-04 slice.
"""
from __future__ import annotations

from datetime import datetime
from math import cos, radians
from typing import Any

from sqlalchemy import select, and_, or_, func, literal
from sqlalchemy.orm import Session

from database.models import Merchant, MenuItem, Review
from core.errors import NotFoundError


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
            # Search in name and cuisine (escape LIKE special chars to prevent injection)
            # Escape backslash first, then % and _ to prevent SQL injection
            escaped_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query_pattern = f"%{escaped_query}%"
            conditions.append(
                or_(
                    Merchant.name.ilike(query_pattern, escape="\\"),
                    Merchant.cuisine.ilike(query_pattern, escape="\\"),
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

    def find_nearby_competitors(
        self,
        *,
        merchant_id: str,
        lat: float,
        lng: float,
        radius_km: float,
        cuisine: str | None = None,
        city: str | None = None,
        limit: int = 20,
    ) -> list[tuple[Merchant, float]]:
        """Return nearby merchants with distance calculated at query time.

        Distance is deliberately not persisted.  The bounding box keeps the
        candidate set small, while the Haversine expression provides the exact
        radius filter in PostgreSQL.
        """
        if radius_km <= 0:
            return []
        lat_delta = radius_km / 111.32
        lng_delta = radius_km / (111.32 * max(abs(cos(radians(lat))), 0.01))
        distance = (
            literal(6371.0)
            * 2
            * func.asin(
                func.sqrt(
                    func.pow(func.sin(func.radians(Merchant.lat - lat) / 2), 2)
                    + func.cos(func.radians(lat))
                    * func.cos(func.radians(Merchant.lat))
                    * func.pow(func.sin(func.radians(Merchant.lng - lng) / 2), 2)
                )
            )
        ).label("distance_km")

        conditions = [
            Merchant.merchant_id != merchant_id,
            Merchant.is_active.is_(True),
            Merchant.lat.is_not(None),
            Merchant.lng.is_not(None),
            Merchant.lat.between(lat - lat_delta, lat + lat_delta),
            Merchant.lng.between(lng - lng_delta, lng + lng_delta),
        ]
        if cuisine:
            conditions.append(Merchant.cuisine == cuisine)
        if city:
            conditions.append(Merchant.city == city)

        stmt = (
            select(Merchant, distance)
            .where(and_(*conditions))
            .where(distance <= radius_km)
            .order_by(distance, Merchant.name)
            .limit(max(1, limit))
        )
        return [(row[0], float(row[1])) for row in self._db.execute(stmt).all()]

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
        opens_at: Any | None = None,
        closes_at: Any | None = None,
    ) -> Merchant:
        """Create a new merchant."""
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
