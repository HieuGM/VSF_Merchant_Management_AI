"""Search & Discovery Tools (`search_merchants`, `search_trending_dishes`).

Supports rich parametric filtering across merchants and market trending dishes,
returning token-efficient compact payloads (strips internal overall_score per C2).
"""
from __future__ import annotations

import json
import math
import statistics
from typing import Any, Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from sqlalchemy.orm import Session

from core.cache import CacheKeys, TTL_CANDIDATES, CachePort
from database.connection import SessionLocal
from database.models import Merchant, MerchantProfile, MarketTrendingDish, MenuItem

from sqlalchemy import or_

_TTL_TRENDING = 10 * 60


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    value = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def normalize_city_slug_and_name(city_input: str | None) -> tuple[list[str], list[str]]:
    """Map any input city string (e.g. 'da_nang', 'da-nang', 'da nang', 'Đà Nẵng')
    to (city_slugs, city_names) for database filtering.
    
    Database values:
      city_slug: 'da_nang', 'tp_hcm', 'ha_noi', 'can_tho', 'hue', 'vung_tau', 'hai_phong', 'khanh_hoa', 'dong_nai'
      city: 'Đà Nẵng', 'TP. HCM', 'Hà Nội', 'Cần Thơ', 'Huế', 'Vũng Tàu', 'Hải Phòng', 'Khánh Hoà', 'Đồng Nai'
    """
    if not city_input:
        return ([], [])
    raw = city_input.strip()
    s = raw.lower().replace("-", " ").replace("_", " ")

    slugs: list[str] = []
    names: list[str] = [raw]

    if "da" in s and ("nang" in s or "năng" in s):
        slugs.append("da_nang")
        names.extend(["Đà Nẵng", "da_nang", "da-nang", "da nang"])
    elif "hcm" in s or "hồ chí minh" in s or "ho chi minh" in s or "saigon" in s or "sài gòn" in s:
        slugs.append("tp_hcm")
        names.extend(["TP. HCM", "tp_hcm", "tp-hcm", "Hồ Chí Minh", "Sài Gòn"])
    elif "ha" in s and ("noi" in s or "nội" in s):
        slugs.append("ha_noi")
        names.extend(["Hà Nội", "ha_noi", "ha-noi", "ha noi"])
    elif "can" in s and ("tho" in s or "thơ" in s):
        slugs.append("can_tho")
        names.extend(["Cần Thơ", "can_tho", "can-tho", "can tho"])
    elif "hue" in s or "huế" in s:
        slugs.append("hue")
        names.extend(["Huế", "hue"])
    elif "vung" in s and ("tau" in s or "tàu" in s):
        slugs.append("vung_tau")
        names.extend(["Vũng Tàu", "vung_tau", "vung-tau", "vung tau"])
    elif "hai" in s and ("phong" in s or "phòng" in s):
        slugs.append("hai_phong")
        names.extend(["Hải Phòng", "hai_phong", "hai-phong", "hai phong"])
    elif "khanh" in s and ("hoa" in s or "hoà" in s):
        slugs.append("khanh_hoa")
        names.extend(["Khánh Hoà", "Khánh Hòa", "khanh_hoa", "khanh-hoa"])
    elif "dong" in s and ("nai" in s):
        slugs.append("dong_nai")
        names.extend(["Đồng Nai", "dong_nai", "dong-nai", "dong nai"])
    else:
        slugs.append(s.replace(" ", "_"))
        names.append(raw)

    return (list(dict.fromkeys(slugs)), list(dict.fromkeys(names)))


from sqlalchemy import cast, String
from database.models import Merchant, MerchantProfile, MarketTrendingDish, MerchantRating


def search_merchants(
    query: str | None = None,
    cuisine: str | None = None,
    city: str | None = None,
    district: str | None = None,
    category: str | None = None,
    ingredient: str | None = None,
    diet: str | None = None,
    taste: str | None = None,
    customer_segment: str | None = None,
    tier: str | None = None,
    price_level: str | None = None,
    min_menu_price: int | None = None,
    max_menu_price: int | None = None,
    min_rating: float | None = None,
    anchor_merchant_id: str | None = None,
    radius_km: float | None = None,
    sort_by: str = "relevance",
    limit: int = 10,
    offset: int = 0,
    db: Session | None = None,
    cache: CachePort | None = None,
) -> dict[str, Any]:
    """Search merchants with rich multi-dimensional parametric filtering across all DB fields."""
    search_q = query or cuisine or ""
    cache_key = (
        CacheKeys.merchant_search(
            query=search_q,
            cuisine=cuisine or "",
            city=city or "",
            budget=price_level or "",
            limit=limit,
        )
        if cache
        and min_menu_price is None
        and max_menu_price is None
        and anchor_merchant_id is None
        and radius_km is None
        else None
    )

    if cache_key and cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    session = db or SessionLocal()
    try:
        stmt = (
            session.query(Merchant, MerchantProfile, MerchantRating)
            .outerjoin(MerchantProfile, Merchant.merchant_id == MerchantProfile.merchant_id)
            .outerjoin(MerchantRating, Merchant.merchant_id == MerchantRating.merchant_id)
            .filter(Merchant.is_active == True)
        )

        if min_menu_price is not None or max_menu_price is not None:
            price_query = session.query(MenuItem.item_id).filter(
                MenuItem.merchant_id == Merchant.merchant_id,
                MenuItem.is_available == True,
            )
            if min_menu_price is not None:
                price_query = price_query.filter(MenuItem.price >= min_menu_price)
            if max_menu_price is not None:
                price_query = price_query.filter(MenuItem.price <= max_menu_price)
            stmt = stmt.filter(price_query.exists())

        # 1. City / City_slug normalization filter
        if city:
            slugs, names = normalize_city_slug_and_name(city)
            city_conditions = (
                [Merchant.city_slug == s for s in slugs] +
                [Merchant.city == n for n in names] +
                [Merchant.city.ilike(f"%{n}%") for n in names] +
                [Merchant.city_slug.ilike(f"%{s}%") for s in slugs]
            )
            stmt = stmt.filter(or_(*city_conditions))

        # 2. General keyword query (matches name, cuisine, category, address, tags)
        if query:
            q_clean = f"%{query.strip()}%"
            stmt = stmt.filter(
                or_(
                    Merchant.name.ilike(q_clean),
                    Merchant.cuisine.ilike(q_clean),
                    Merchant.category.ilike(q_clean),
                    Merchant.address.ilike(q_clean),
                    cast(Merchant.ingredient_tags, String).ilike(q_clean),
                    cast(Merchant.diet_tags, String).ilike(q_clean),
                    cast(Merchant.taste_tags, String).ilike(q_clean),
                    cast(Merchant.customer_segments, String).ilike(q_clean),
                )
            )

        # 3. Cuisine filter (matches cuisine OR name)
        if cuisine:
            c_clean = f"%{cuisine.strip()}%"
            stmt = stmt.filter(
                or_(
                    Merchant.cuisine.ilike(c_clean),
                    Merchant.name.ilike(c_clean),
                )
            )

        # 4. Category filter
        if category:
            stmt = stmt.filter(Merchant.category.ilike(f"%{category.strip()}%"))

        # 5. Ingredient tag filter (bò, gà, hải sản, heo,...)
        if ingredient:
            stmt = stmt.filter(cast(Merchant.ingredient_tags, String).ilike(f"%{ingredient.strip()}%"))

        # 6. Diet tag filter (chay, eat clean, keto,...)
        if diet:
            stmt = stmt.filter(cast(Merchant.diet_tags, String).ilike(f"%{diet.strip()}%"))

        # 7. Taste tag filter (cay, ngọt, mặn,...)
        if taste:
            stmt = stmt.filter(cast(Merchant.taste_tags, String).ilike(f"%{taste.strip()}%"))

        # 8. Customer segment tag filter (gia đình, học sinh, dân văn phòng,...)
        if customer_segment:
            stmt = stmt.filter(cast(Merchant.customer_segments, String).ilike(f"%{customer_segment.strip()}%"))

        # 9. District filter
        if district:
            d = district.strip()
            if d.lower().startswith("q") and d[1:].strip().isdigit():
                q_num = d[1:].strip()
                stmt = stmt.filter(
                    or_(
                        Merchant.address.ilike(f"%Quận {q_num}%"),
                        Merchant.address.ilike(f"%Q.{q_num}%"),
                        Merchant.address.ilike(f"%Q{q_num}%"),
                    )
                )
            else:
                stmt = stmt.filter(Merchant.address.ilike(f"%{d}%"))

        # 10. Tier & Price level filter
        if tier:
            stmt = stmt.filter(MerchantProfile.tier == tier.strip())
        if price_level:
            stmt = stmt.filter(MerchantProfile.price_level == price_level.strip())

        # 11. Min rating filter (ShopeeFood or Foody rating)
        if min_rating is not None:
            stmt = stmt.filter(
                or_(
                    MerchantRating.shopeefood_rating >= min_rating,
                    MerchantRating.foody_rating >= min_rating,
                )
            )

        anchor: Merchant | None = None
        if anchor_merchant_id:
            anchor = session.get(Merchant, anchor_merchant_id)
        effective_radius = radius_km if (anchor and radius_km is not None) else None
        row_limit = 200 if effective_radius is not None else min(limit, 25)
        rows = stmt.offset(offset).limit(row_limit).all()
        results: list[dict[str, Any]] = []

        for m, p, r in rows:
            distance_km: float | None = None
            if (
                effective_radius is not None
                and anchor is not None
                and anchor.lat is not None
                and anchor.lng is not None
                and m.lat is not None
                and m.lng is not None
            ):
                distance_km = _haversine_km(anchor.lat, anchor.lng, m.lat, m.lng)
                if distance_km > effective_radius:
                    continue
            elif effective_radius is not None:
                continue

            prices = [
                int(value[0])
                for value in (
                    session.query(MenuItem.price)
                    .filter(
                        MenuItem.merchant_id == m.merchant_id,
                        MenuItem.is_available == True,
                    )
                    .order_by(MenuItem.price)
                    .all()
                )
            ]
            item = {
                "merchant_id": m.merchant_id,
                "name": m.name,
                "cuisine": m.cuisine,
                "category": m.category,
                "city": m.city,
                "city_slug": m.city_slug,
                "address": m.address,
                "price_level": p.price_level if p else "trung bình",
                "menu_price_min": min(prices) if prices else None,
                "menu_price_median": (
                    int(statistics.median(prices)) if prices else None
                ),
                "menu_price_max": max(prices) if prices else None,
                "tier": p.tier if p else None,
                "ratings": {
                    "shopeefood": float(r.shopeefood_rating) if (r and r.shopeefood_rating) else None,
                    "foody": float(r.foody_rating) if (r and r.foody_rating) else None,
                },
                "tags": {
                    "taste": m.taste_tags or [],
                    "diet": m.diet_tags or [],
                    "ingredient": m.ingredient_tags or [],
                    "customer_segments": m.customer_segments or [],
                },
                "is_active": m.is_active,
                "distance_km": (
                    round(distance_km, 2) if distance_km is not None else None
                ),
            }
            results.append(item)

        if sort_by == "distance":
            results.sort(
                key=lambda item: (
                    item["distance_km"] is None,
                    item["distance_km"] or math.inf,
                    item["name"],
                )
            )
        elif sort_by == "rating":
            def _rating(item: dict[str, Any]) -> float:
                ratings = item["ratings"]
                if ratings.get("shopeefood") is not None:
                    return float(ratings["shopeefood"])
                if ratings.get("foody") is not None:
                    return float(ratings["foody"]) / 2
                return -1

            results.sort(key=lambda item: (-_rating(item), item["name"]))

        results = results[: min(limit, 25)]

        result = {
            "status": "ok",
            "count": len(results),
            "merchants": results,
        }

        if cache_key and cache:
            cache.set(cache_key, result, ttl_seconds=TTL_CANDIDATES)

        return result
    finally:
        if db is None:
            session.close()


def search_trending_dishes(
    cuisine: str | None = None,
    city_slug: str | None = None,
    limit: int = 5,
    db: Session | None = None,
    cache: CachePort | None = None,
) -> dict[str, Any]:
    """Query top trending food items from market_trending_dishes."""
    cache_key = CacheKeys.trending_dishes(city_slug or "", cuisine or "") if cache else None

    if cache_key and cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    session = db or SessionLocal()
    try:
        stmt = session.query(MarketTrendingDish)
        if city_slug:
            slugs, names = normalize_city_slug_and_name(city_slug)
            city_conditions = (
                [MarketTrendingDish.city_slug == s for s in slugs] +
                [MarketTrendingDish.city_slug == n for n in names] +
                [MarketTrendingDish.city_slug.ilike(f"%{s}%") for s in slugs] +
                [MarketTrendingDish.city_slug.ilike(f"%{n}%") for n in names]
            )
            stmt = stmt.filter(or_(*city_conditions))

        if cuisine:
            stmt = stmt.filter(
                or_(
                    MarketTrendingDish.cuisine.ilike(f"%{cuisine.strip()}%"),
                    MarketTrendingDish.dish_name.ilike(f"%{cuisine.strip()}%"),
                )
            )

        dishes = stmt.order_by(MarketTrendingDish.rank.asc()).limit(min(limit, 10)).all()
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
        result = {
            "status": "ok",
            "count": len(results),
            "trending_dishes": results,
        }

        if cache_key and cache:
            cache.set(cache_key, result, ttl_seconds=_TTL_TRENDING)

        return result
    finally:
        if db is None:
            session.close()


# --- CrewAI Tool Classes ---

from typing import Literal

CitySlug = Literal[
    "da_nang",
    "tp_hcm",
    "ha_noi",
    "can_tho",
    "hue",
    "vung_tau",
    "hai_phong",
    "khanh_hoa",
    "dong_nai",
]


class SearchMerchantsInput(BaseModel):
    query: str | None = Field(None, description="General search keyword for restaurant name, dish, or concept (e.g. 'sushi', 'cơm tấm', 'lẩu', 'gia đình')")
    city: str | None = Field(None, description="City name or slug filter. Valid city_slugs: 'da_nang', 'tp_hcm', 'ha_noi', 'can_tho', 'hue', 'vung_tau', 'hai_phong', 'khanh_hoa', 'dong_nai'")
    cuisine: str | None = Field(None, description="Cuisine type filter (e.g. 'Món Nhật', 'Món Việt', 'Café/Dessert')")
    category: str | None = Field(None, description="Category filter (e.g. 'Quán ăn', 'Nhà hàng', 'Café/Dessert')")
    district: str | None = Field(None, description="District filter (e.g. 'Quận 1', 'Bình Thạnh', 'Hải Châu', 'Q1')")
    ingredient: str | None = Field(None, description="Ingredient tag filter (e.g. 'bò', 'gà', 'hải sản', 'heo', 'tôm')")
    diet: str | None = Field(None, description="Diet tag filter (e.g. 'chay', 'eat clean', 'keto')")
    taste: str | None = Field(None, description="Taste tag filter (e.g. 'cay', 'chua', 'ngọt', 'đậm đà')")
    customer_segment: str | None = Field(None, description="Customer segment tag filter (e.g. 'gia đình', 'học sinh sinh viên', 'dân văn phòng', 'cặp đôi')")
    tier: Literal["hero", "background"] | None = Field(None, description="Merchant tier filter.")
    price_level: Literal["rẻ", "trung bình", "cao cấp"] | None = Field(None, description="Price level segment.")
    min_menu_price: int | None = Field(None, ge=0, description="Minimum available menu item price in VND.")
    max_menu_price: int | None = Field(None, ge=0, description="Maximum affordable menu item price in VND.")
    min_rating: float | None = Field(None, description="Minimum platform rating threshold (0.0 .. 5.0).")
    anchor_merchant_id: str | None = Field(None, description="Owner merchant used as the center of a nearby search.")
    radius_km: float | None = Field(None, ge=0.5, le=20, description="Radius around anchor merchant in kilometers.")
    sort_by: Literal["relevance", "rating", "distance"] = Field("relevance", description="Deterministic result ordering.")
    limit: int = Field(10, description="Max results (1..25)")


class SearchMerchantsTool(BaseTool):
    name: str = "search_merchants"
    description: str = (
        "Search restaurants using rich multi-dimensional parametric filters (query, city, district, cuisine, "
        "category, ingredient tags, diet tags, taste tags, customer segment tags, tier, price level, min rating). "
        "Returns compact list of matching merchant profiles from the database."
    )
    args_schema: Type[BaseModel] = SearchMerchantsInput

    def _run(
        self,
        query: str | None = None,
        cuisine: str | None = None,
        city: str | None = None,
        district: str | None = None,
        category: str | None = None,
        ingredient: str | None = None,
        diet: str | None = None,
        taste: str | None = None,
        customer_segment: str | None = None,
        tier: str | None = None,
        price_level: str | None = None,
        min_menu_price: int | None = None,
        max_menu_price: int | None = None,
        min_rating: float | None = None,
        anchor_merchant_id: str | None = None,
        radius_km: float | None = None,
        sort_by: str = "relevance",
        limit: int = 10,
    ) -> str:
        from core.dependencies import get_cache
        res = search_merchants(
            query=query,
            cuisine=cuisine,
            city=city,
            district=district,
            category=category,
            ingredient=ingredient,
            diet=diet,
            taste=taste,
            customer_segment=customer_segment,
            tier=tier,
            price_level=price_level,
            min_menu_price=min_menu_price,
            max_menu_price=max_menu_price,
            min_rating=min_rating,
            anchor_merchant_id=anchor_merchant_id,
            radius_km=radius_km,
            sort_by=sort_by,
            limit=limit,
            cache=get_cache(),
        )
        return json.dumps(res, ensure_ascii=False)


class SearchTrendingDishesInput(BaseModel):
    cuisine: str | None = Field(None, description="Target cuisine segment or dish keyword, e.g., 'Món Việt', 'Trà sữa', 'sushi'")
    city_slug: str | None = Field(None, description="Target city_slug. Valid values: 'da_nang', 'tp_hcm', 'ha_noi', 'can_tho', 'hue', 'vung_tau', 'hai_phong', 'khanh_hoa', 'dong_nai'")
    limit: int = Field(5, description="Number of top trending dishes to return (1..10)")


class SearchTrendingDishesTool(BaseTool):
    name: str = "search_trending_dishes"
    description: str = "Query high-growth trending dishes in a target city or cuisine segment from system database."
    args_schema: Type[BaseModel] = SearchTrendingDishesInput

    def _run(self, cuisine: str | None = None, city_slug: str | None = None, limit: int = 5) -> str:
        from core.dependencies import get_cache
        res = search_trending_dishes(
            cuisine=cuisine,
            city_slug=city_slug,
            limit=limit,
            cache=get_cache(),
        )
        return json.dumps(res, ensure_ascii=False)
