"""Merchant repository (C-01) — data access layer for UC-04 search.

Provides CRUD and search operations for merchants, menu items, and reviews.
Phase 0b: basic query + geo search foundation for UC-04 slice.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session

from database.models import Merchant, MenuItem, Review
from core.errors import NotFoundError
from services.geo.h3_index import H3CandidateIndex


class MerchantRepository:
    """Repository for merchant data access with search capabilities."""

    def __init__(self, db: Session, h3_index: H3CandidateIndex | None = None) -> None:
        self._db = db
        self._h3_index = h3_index or H3CandidateIndex()

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

    def get_by_ids(self, merchant_ids: list[str]) -> list[Merchant]:
        """Fetch a bounded set of active merchants by their already-retrieved IDs."""
        ids = list(dict.fromkeys(str(value) for value in merchant_ids if value))[:100]
        if not ids:
            return []
        stmt = (
            select(Merchant)
            .where(Merchant.merchant_id.in_(ids), Merchant.is_active.is_(True))
            .order_by(Merchant.name)
        )
        return list(self._db.execute(stmt).scalars().all())

    def list_demo_targets(self) -> list[Merchant]:
        """Return active owner merchants that may be selected by the demo UI."""
        stmt = (
            select(Merchant)
            .where(
                Merchant.is_demo_target.is_(True),
                Merchant.is_active.is_(True),
            )
            .order_by(Merchant.name, Merchant.merchant_id)
        )
        return list(self._db.execute(stmt).scalars().all())

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

        if lat is not None and lng is not None and radius_km is not None:
            conditions.append(
                Merchant.merchant_h3_cell.in_(
                    self._h3_index.cells_for_radius(lat, lng, radius_km)
                )
            )

        if conditions:
            stmt = stmt.where(and_(*conditions))

        stmt = stmt.distinct().order_by(Merchant.name).limit(limit).offset(offset)
        result = self._db.execute(stmt).scalars().all()
        return list(result)

    def find_nearby_candidates(
        self,
        *,
        lat: float,
        lng: float,
        radius_km: float,
        cuisine: str | None = None,
        city: str | None = None,
        exclude_merchant_id: str | None = None,
        limit: int = 20,
    ) -> list[Merchant]:
        """Return nearby candidates constrained by their indexed H3 cells.

        This deliberately does not attach an exact distance.  A dedicated
        PostGIS or routing adapter can rank this already-bounded set later.
        """
        if radius_km <= 0:
            return []

        conditions = [Merchant.is_active.is_(True)]
        if exclude_merchant_id:
            conditions.append(Merchant.merchant_id != exclude_merchant_id)
        if cuisine:
            conditions.append(Merchant.cuisine == cuisine)
        if city:
            conditions.append(Merchant.city == city)

        attempts = (
            (9, Merchant.h3_index_9, radius_km),
            (8, Merchant.merchant_h3_cell, radius_km * 2),
            (6, Merchant.h3_index_6, radius_km * 4),
        )
        for resolution, h3_column, attempt_radius in attempts:
            stmt = (
                select(Merchant)
                .where(
                    and_(
                        *conditions,
                        h3_column.in_(
                            H3CandidateIndex(
                                resolution=resolution
                            ).cells_for_radius(lat, lng, attempt_radius)
                        ),
                    )
                )
                .order_by(Merchant.name)
                .limit(max(1, limit))
            )
            candidates = list(self._db.execute(stmt).scalars().all())
            if candidates:
                return candidates
        return []

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
    ) -> list[Merchant]:
        """Backward-compatible semantic alias for H3 nearby candidates."""
        return self.find_nearby_candidates(
            lat=lat,
            lng=lng,
            radius_km=radius_km,
            cuisine=cuisine,
            city=city,
            exclude_merchant_id=merchant_id,
            limit=limit,
        )

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
