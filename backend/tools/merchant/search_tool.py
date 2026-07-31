"""Public merchant search with adaptive H3 nearby expansion.

Supports rich filtering and token-efficient public projections.
"""
from __future__ import annotations

import math
import re
import statistics
import time
from typing import Any, Callable
from pydantic import BaseModel, Field
from sqlalchemy import String, and_, cast, or_
from sqlalchemy.orm import Session

from core.cache import CacheKeys, TTL_CANDIDATES, CachePort
from core.logging import get_logger
from database.connection import SessionLocal
from database.models import Merchant, MerchantProfile, MerchantRating, MenuItem
from models.merchant_agentic import normalize_city_slugs, normalize_text
from services.geo.h3_index import H3CandidateIndex, haversine_km

CacheEventCallback = Callable[[dict[str, Any]], None]
logger = get_logger(__name__)


def _emit_cache_event(
    callback: CacheEventCallback | None,
    payload: dict[str, Any],
) -> None:
    if callback is None:
        return
    try:
        callback(payload)
    except Exception:
        logger.debug("Cache trace callback failed", exc_info=True)


def _keyword_match_predicate(keyword: str):
    """Require all meaningful terms while still preferring an exact phrase."""

    def match(value: str):
        pattern = f"%{value}%"
        return or_(
            Merchant.name.ilike(pattern),
            Merchant.cuisine.ilike(pattern),
            Merchant.category.ilike(pattern),
            Merchant.address.ilike(pattern),
            cast(Merchant.ingredient_tags, String).ilike(pattern),
            cast(Merchant.diet_tags, String).ilike(pattern),
            cast(Merchant.taste_tags, String).ilike(pattern),
            cast(Merchant.customer_segments, String).ilike(pattern),
        )

    def menu_match(value: str):
        return (
            MenuItem.__table__.select()
            .where(
                MenuItem.merchant_id == Merchant.merchant_id,
                MenuItem.is_available == True,
                MenuItem.name.ilike(f"%{value}%"),
            )
            .exists()
        )

    phrase = keyword.strip()
    terms = list(
        dict.fromkeys(
            term
            for term in re.findall(r"[\wÀ-ỹ]+", phrase, flags=re.UNICODE)
            if len(term) > 1 and term.casefold() not in {"quán", "quan", "nhà", "hàng"}
        )
    )
    exact = or_(match(phrase), menu_match(phrase))
    if not terms:
        return exact
    all_terms = and_(*(or_(match(term), menu_match(term)) for term in terms))
    return or_(exact, all_terms)


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
    cache_event_callback: CacheEventCallback | None = None,
) -> dict[str, Any]:
    """Search merchants with rich multi-dimensional parametric filtering across all DB fields."""
    cache_key = (
        CacheKeys.merchant_search_filters(
            {
                "query": query,
                "cuisine": cuisine,
                "city": city,
                "district": district,
                "category": category,
                "ingredient": ingredient,
                "diet": diet,
                "taste": taste,
                "customer_segment": customer_segment,
                "tier": tier,
                "price_level": price_level,
                "min_menu_price": min_menu_price,
                "max_menu_price": max_menu_price,
                "min_rating": min_rating,
                "anchor_merchant_id": anchor_merchant_id,
                "radius_km": radius_km,
                "sort_by": sort_by,
                "limit": limit,
                "offset": offset,
            }
        )
        if cache
        else None
    )

    cache_backend = type(cache).__name__ if cache is not None else "disabled"
    if cache_key and cache:
        cache_started = time.perf_counter()
        cached = cache.get(cache_key)
        cache_duration_ms = round(
            (time.perf_counter() - cache_started) * 1000,
            3,
        )
        _emit_cache_event(
            cache_event_callback,
            {
                "tool_name": "search_merchants",
                "operation": "lookup",
                "status": "hit" if cached is not None else "miss",
                "cache_key": cache_key,
                "backend": cache_backend,
                "ttl_seconds": TTL_CANDIDATES,
                "duration_ms": cache_duration_ms,
            },
        )
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
            normalized_city_slugs = normalize_city_slugs(city)
            city_slugs = (
                [slug for slug in normalized_city_slugs.split(",") if slug]
                if normalized_city_slugs
                else []
            )
            stmt = stmt.filter(Merchant.city_slug.in_(city_slugs))

        # 2. General keyword query (matches name, cuisine, category, address, tags)
        if query:
            stmt = stmt.filter(_keyword_match_predicate(query))

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
        selected_h3_resolution: int | None = None
        expanded_search = False
        if effective_radius is not None:
            if anchor.lat is None or anchor.lng is None:
                return {"status": "ok", "count": 0, "merchants": []}
            stmt = stmt.filter(Merchant.merchant_id != anchor.merchant_id)
            h3_attempts = (
                (9, Merchant.h3_index_9, float(effective_radius)),
                (8, Merchant.merchant_h3_cell, float(effective_radius) * 2),
                (6, Merchant.h3_index_6, float(effective_radius) * 4),
            )
            rows = []
            for resolution, column, attempt_radius in h3_attempts:
                selected_h3_resolution = resolution
                effective_radius = attempt_radius
                expanded_search = resolution != 9
                candidate_rows = (
                    stmt.filter(
                        column.in_(
                            H3CandidateIndex(resolution=resolution).cells_for_radius(
                                anchor.lat,
                                anchor.lng,
                                attempt_radius,
                            )
                        )
                    )
                    .offset(offset)
                    .limit(200)
                    .all()
                )
                rows = [
                    row
                    for row in candidate_rows
                    if row[0].lat is not None
                    and row[0].lng is not None
                    and haversine_km(
                        anchor.lat,
                        anchor.lng,
                        row[0].lat,
                        row[0].lng,
                    )
                    <= attempt_radius
                ]
                if rows:
                    break
        else:
            rows = (
                stmt.offset(offset)
                .limit(200 if query else min(limit, 25))
                .all()
            )

        merchant_ids = [row[0].merchant_id for row in rows]
        prices_by_merchant: dict[str, list[int]] = {
            merchant_id: [] for merchant_id in merchant_ids
        }
        menu_names_by_merchant: dict[str, list[str]] = {
            merchant_id: [] for merchant_id in merchant_ids
        }
        if merchant_ids:
            price_rows = (
                session.query(MenuItem.merchant_id, MenuItem.name, MenuItem.price)
                .filter(
                    MenuItem.merchant_id.in_(merchant_ids),
                    MenuItem.is_available == True,
                )
                .order_by(MenuItem.merchant_id, MenuItem.price, MenuItem.name)
                .all()
            )
            for merchant_id, menu_name, price in price_rows:
                prices_by_merchant[str(merchant_id)].append(int(price))
                menu_names_by_merchant[str(merchant_id)].append(str(menu_name))

        results: list[dict[str, Any]] = []

        for m, p, r in rows:
            prices = prices_by_merchant.get(str(m.merchant_id), [])
            distance_km = (
                haversine_km(anchor.lat, anchor.lng, m.lat, m.lng)
                if anchor is not None
                and anchor.lat is not None
                and anchor.lng is not None
                and m.lat is not None
                and m.lng is not None
                else None
            )
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
                "_search_menu_names": menu_names_by_merchant.get(str(m.merchant_id), []),
                "distance_km": (
                    round(distance_km, 2) if distance_km is not None else None
                ),
            }
            results.append(item)

        if sort_by == "distance":
            results.sort(
                key=lambda item: (
                    item["distance_km"] is None,
                    item["distance_km"] if item["distance_km"] is not None else math.inf,
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
        elif query:
            normalized_phrase = normalize_text(query)
            query_terms = normalized_phrase.split()

            def _relevance(item: dict[str, Any]) -> tuple[int, str]:
                name = normalize_text(str(item.get("name") or ""))
                cuisine_text = normalize_text(str(item.get("cuisine") or ""))
                menu_text = normalize_text(
                    " ".join(item.get("_search_menu_names") or [])
                )
                score = 0
                if normalized_phrase in name:
                    score += 100
                if normalized_phrase in cuisine_text:
                    score += 60
                if normalized_phrase in menu_text:
                    score += 50
                score += sum(12 for term in query_terms if term in name)
                score += sum(6 for term in query_terms if term in cuisine_text)
                score += sum(3 for term in query_terms if term in menu_text)
                return (-score, str(item["name"]))

            results.sort(key=_relevance)

        results = results[: min(limit, 25)]
        for item in results:
            item.pop("_search_menu_names", None)

        result = {
            "status": "ok",
            "count": len(results),
            "merchants": results,
        }
        if selected_h3_resolution is not None:
            result.update(
                {
                    "h3_resolution": selected_h3_resolution,
                    "effective_radius_km": float(effective_radius),
                    "expanded_search": expanded_search,
                }
            )

        if cache_key and cache:
            cache_started = time.perf_counter()
            cache.set(cache_key, result, ttl_seconds=TTL_CANDIDATES)
            _emit_cache_event(
                cache_event_callback,
                {
                    "tool_name": "search_merchants",
                    "operation": "set",
                    "status": "store",
                    "cache_key": cache_key,
                    "backend": cache_backend,
                    "ttl_seconds": TTL_CANDIDATES,
                    "duration_ms": round(
                        (time.perf_counter() - cache_started) * 1000,
                        3,
                    ),
                },
            )

        return result
    finally:
        if db is None:
            session.close()


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
    city: str | None = Field(None, description="City name or slug filter. Valid city_slugs format must be in snake format (e.g. 'da_nang', 'tp_hcm', 'ha_noi') or list separated by commas (e.g. 'da_nang, tp_hcm').")
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
