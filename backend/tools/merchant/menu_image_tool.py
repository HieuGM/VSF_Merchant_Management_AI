"""Menu & Food Images Tool (Task 3).

Returns menu items with image URLs and image quality metadata.
NEVER passes image pixels to LLMs — only URLs and quality scores.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import FoodImage, MenuItem


def get_menu_and_food_images(
    merchant_id: str,
    only_with_images: bool = False,
    min_image_quality: float | None = None,
    category: str | None = None,
    limit: int = 10,
    db: Session | None = None,
) -> dict[str, Any]:
    """Return menu items with image URLs and quality metadata for a merchant.

    Args:
        merchant_id: Target merchant ID.
        only_with_images: If True, only return items that have at least one image.
        min_image_quality: If set, filter images with dish_image_quality >= this value.
        category: Optional menu item category filter.
        limit: Max menu items to return (1..20).
        db: Optional injected DB session.

    Returns:
        dict with status, items list (each with image_urls, quality scores, price).
        Images are returned as URL strings only — no pixel data.
    """
    session = db or SessionLocal()
    try:
        query = session.query(MenuItem).filter(
            MenuItem.merchant_id == merchant_id,
            MenuItem.is_available == True,
        )
        if category:
            query = query.filter(MenuItem.category.ilike(f"%{category.strip()}%"))
        if only_with_images:
            query = query.filter(MenuItem.has_photo == True)

        items = query.order_by(MenuItem.total_like.desc()).limit(min(limit, 20)).all()

        result_items: list[dict[str, Any]] = []
        for item in items:
            # Get associated images
            img_query = session.query(FoodImage).filter(FoodImage.item_id == item.item_id)
            if min_image_quality is not None:
                img_query = img_query.filter(
                    FoodImage.dish_image_quality >= min_image_quality
                )
            images = img_query.order_by(FoodImage.dish_image_quality.desc().nulls_last()).all()

            img_data = [
                {
                    "url": img.url,
                    "dish_image_quality": float(img.dish_image_quality) if img.dish_image_quality else None,
                    "blur_score": float(img.blur_score) if img.blur_score else None,
                }
                for img in images
            ]

            result_items.append({
                "item_id": item.item_id,
                "name": item.name,
                "price": item.price,
                "discount_price": item.discount_price,
                "category": item.category,
                "total_like": item.total_like,
                "has_photo": item.has_photo,
                "images": img_data,
            })

        return {
            "status": "ok",
            "merchant_id": merchant_id,
            "count": len(result_items),
            "items": result_items,
        }
    finally:
        if db is None:
            session.close()


class GetMenuAndFoodImagesInput(BaseModel):
    merchant_id: str = Field(..., description="Merchant ID to fetch menu and food images for.")
    only_with_images: bool = Field(False, description="If True, only return menu items that have images.")
    min_image_quality: Optional[float] = Field(
        None,
        description="Minimum dish_image_quality score (0.0 to 1.0) to filter images.",
    )
    category: Optional[str] = Field(None, description="Filter menu items by category keyword.")
    limit: int = Field(10, description="Max number of menu items to return (1..20).")
