"""Policy-safe public merchant detail retrieval for conversational follow-ups."""
from __future__ import annotations

import time
from typing import Any, Callable

from sqlalchemy.orm import Session

from core.cache import CacheKeys, CachePort, TTL_PROFILE_SNAPSHOT
from database.connection import SessionLocal
from database.models import Merchant, MerchantRating, MenuItem


CacheEventCallback = Callable[[dict[str, Any]], None]


def get_public_merchant_detail(
    merchant_id: str,
    *,
    menu_limit: int = 20,
    db: Session | None = None,
    cache: CachePort | None = None,
    cache_event_callback: CacheEventCallback | None = None,
) -> dict[str, Any]:
    """Return public identity, hours, location, ratings, and available menu."""
    cache_key = CacheKeys.merchant_public_detail(str(merchant_id)) if cache else None
    cache_backend = type(cache).__name__ if cache is not None else "disabled"
    if cache_key and cache:
        started = time.perf_counter()
        cached = cache.get(cache_key)
        if cache_event_callback:
            cache_event_callback(
                {
                    "tool_name": "get_public_merchant_detail",
                    "operation": "lookup",
                    "status": "hit" if cached is not None else "miss",
                    "cache_key": cache_key,
                    "backend": cache_backend,
                    "ttl_seconds": TTL_PROFILE_SNAPSHOT,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                }
            )
        if cached is not None:
            return cached

    session = db or SessionLocal()
    try:
        row = (
            session.query(Merchant, MerchantRating)
            .outerjoin(
                MerchantRating,
                Merchant.merchant_id == MerchantRating.merchant_id,
            )
            .filter(
                Merchant.merchant_id == str(merchant_id),
                Merchant.is_active == True,
            )
            .first()
        )
        if row is None:
            return {"status": "not_found", "merchant_id": str(merchant_id)}

        merchant, rating = row
        menu_items = (
            session.query(MenuItem)
            .filter(
                MenuItem.merchant_id == merchant.merchant_id,
                MenuItem.is_available == True,
            )
            .order_by(MenuItem.total_like.desc(), MenuItem.name)
            .limit(min(max(menu_limit, 1), 50))
            .all()
        )
        result = {
            "status": "ok",
            "merchant_id": merchant.merchant_id,
            "name": merchant.name,
            "cuisine": merchant.cuisine,
            "category": merchant.category,
            "address": merchant.address,
            "city": merchant.city,
            "city_slug": merchant.city_slug,
            "lat": merchant.lat,
            "lng": merchant.lng,
            "opens_at": merchant.opens_at.isoformat() if merchant.opens_at else None,
            "closes_at": merchant.closes_at.isoformat() if merchant.closes_at else None,
            "timezone": merchant.timezone,
            "ratings": {
                "shopeefood": (
                    float(rating.shopeefood_rating)
                    if rating and rating.shopeefood_rating is not None
                    else None
                ),
                "foody": (
                    float(rating.foody_rating)
                    if rating and rating.foody_rating is not None
                    else None
                ),
            },
            "menu_items": [
                {
                    "name": item.name,
                    "price": item.price,
                    "discount_price": item.discount_price,
                    "category": item.category,
                }
                for item in menu_items
            ],
        }
        if cache_key and cache:
            started = time.perf_counter()
            cache.set(cache_key, result, ttl_seconds=TTL_PROFILE_SNAPSHOT)
            if cache_event_callback:
                cache_event_callback(
                    {
                        "tool_name": "get_public_merchant_detail",
                        "operation": "set",
                        "status": "store",
                        "cache_key": cache_key,
                        "backend": cache_backend,
                        "ttl_seconds": TTL_PROFILE_SNAPSHOT,
                        "duration_ms": round(
                            (time.perf_counter() - started) * 1000, 3
                        ),
                    }
                )
        return result
    finally:
        if db is None:
            session.close()

