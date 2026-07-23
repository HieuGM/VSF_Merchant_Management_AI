"""Search & Discovery Tools (`search_merchants`, `search_trending_dishes`).

Supports rich parametric filtering across merchants and market trending dishes,
returning token-efficient compact payloads (strips internal overall_score per C2).
"""
from __future__ import annotations

import json
from typing import Any, Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from sqlalchemy.orm import Session
from database.connection import SessionLocal
from database.models import Merchant, MerchantProfile, MarketTrendingDish


def search_merchants(
    cuisine: str | None = None,
    city: str | None = None,
    district: str | None = None,
    price_level: str | None = None,
    min_rating: float | None = None,
    limit: int = 10,
    offset: int = 0,
    db: Session | None = None,
) -> dict[str, Any]:
    """Search merchants with intuitive filtering parameters."""
    session = db or SessionLocal()
    try:
        query = (
            session.query(Merchant, MerchantProfile)
            .outerjoin(MerchantProfile, Merchant.merchant_id == MerchantProfile.merchant_id)
            .filter(Merchant.is_active == True)
        )

        if cuisine:
            c = cuisine.strip()
            query = query.filter((Merchant.cuisine == c) | (Merchant.cuisine.ilike(f"%{c}%")))
        if city:
            ci = city.strip()
            query = query.filter((Merchant.city == ci) | (Merchant.city.ilike(f"%{ci}%")))
        if district:
            d = district.strip()
            query = query.filter(Merchant.address.ilike(f"%{d}%"))
        if price_level:
            query = query.filter(MerchantProfile.price_level == price_level.strip())

        rows = query.offset(offset).limit(min(limit, 25)).all()
        results: list[dict[str, Any]] = []

        for m, p in rows:
            item = {
                "merchant_id": m.merchant_id,
                "name": m.name,
                "cuisine": m.cuisine,
                "city": m.city,
                "address": m.address,
                "price_level": p.price_level if p else "trung bình",
                "is_active": m.is_active,
            }
            results.append(item)

        return {
            "status": "ok",
            "count": len(results),
            "merchants": results,
        }
    finally:
        if db is None:
            session.close()


def search_trending_dishes(
    cuisine: str | None = None,
    city_slug: str | None = "ha-noi",
    limit: int = 5,
    db: Session | None = None,
) -> dict[str, Any]:
    """Query top trending food items from market_trending_dishes."""
    session = db or SessionLocal()
    try:
        query = session.query(MarketTrendingDish)
        if city_slug:
            query = query.filter(MarketTrendingDish.city_slug == city_slug.strip().lower())
        if cuisine:
            query = query.filter(MarketTrendingDish.cuisine.ilike(f"%{cuisine.strip()}%"))

        dishes = query.order_by(MarketTrendingDish.rank.asc()).limit(min(limit, 10)).all()
        results = [
            {
                "dish_name": d.dish_name,
                "cuisine": d.cuisine,
                "city_slug": d.city_slug,
                "trend_score": float(d.trend_score),
                "rank": d.rank,
            }
            for d in dishes
        ]
        return {
            "status": "ok",
            "count": len(results),
            "trending_dishes": results,
        }
    finally:
        if db is None:
            session.close()


# --- CrewAI Tool Classes ---

class SearchMerchantsInput(BaseModel):
    cuisine: str | None = Field(None, description="Cuisine type filter, e.g., 'Món Việt', 'Trà sữa'")
    city: str | None = Field(None, description="City filter, e.g., 'TP. HCM' or 'Hà Nội'")
    district: str | None = Field(None, description="District filter, e.g., 'Q1', 'Bình Thạnh'")
    price_level: str | None = Field(None, description="Price level: 'bình dân', 'trung bình', 'cao cấp'")
    limit: int = Field(10, description="Max results (1..25)")


class SearchMerchantsTool(BaseTool):
    name: str = "search_merchants"
    description: str = (
        "Search restaurants by cuisine, city, district, or price level. "
        "Returns compact list of matching merchant profiles."
    )
    args_schema: Type[BaseModel] = SearchMerchantsInput

    def _run(
        self,
        cuisine: str | None = None,
        city: str | None = None,
        district: str | None = None,
        price_level: str | None = None,
        limit: int = 10,
    ) -> str:
        res = search_merchants(
            cuisine=cuisine,
            city=city,
            district=district,
            price_level=price_level,
            limit=limit,
        )
        return json.dumps(res, ensure_ascii=False)


class SearchTrendingDishesInput(BaseModel):
    cuisine: str | None = Field(None, description="Target cuisine segment")
    city_slug: str | None = Field("ha-noi", description="Target city slug, e.g., 'ha-noi', 'tp-hcm'")
    limit: int = Field(5, description="Number of top trending dishes to return")


class SearchTrendingDishesTool(BaseTool):
    name: str = "search_trending_dishes"
    description: str = "Query high-growth trending dishes in a target city or cuisine segment."
    args_schema: Type[BaseModel] = SearchTrendingDishesInput

    def _run(self, cuisine: str | None = None, city_slug: str | None = "ha-noi", limit: int = 5) -> str:
        res = search_trending_dishes(cuisine=cuisine, city_slug=city_slug, limit=limit)
        return json.dumps(res, ensure_ascii=False)
