"""Owner review retrieval with deterministic sentiment/theme aggregation."""
from __future__ import annotations

from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import Review


_THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "food_quality": (
        "ngon",
        "dở",
        "nhạt",
        "mặn",
        "nguội",
        "chất lượng món",
    ),
    "delivery": ("giao", "ship", "chậm", "trễ"),
    "packaging": ("đóng gói", "bao bì", "hộp", "túi", "bị đổ"),
    "service": ("phục vụ", "nhân viên", "thái độ"),
    "price": ("giá", "đắt", "rẻ"),
    "hygiene": ("vệ sinh", "bẩn", "sạch"),
    "image": ("ảnh", "hình"),
}


def _review_themes(rows: list[Review]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        text = row.text.lower()
        for theme, keywords in _THEME_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                counts[theme] += 1
    return dict(counts.most_common())


def _rating_distribution(rows: list[Review]) -> dict[str, int]:
    distribution = {str(i): 0 for i in range(1, 11)}
    for row in rows:
        if row.rating is None:
            continue
        bucket = str(max(1, min(10, round(float(row.rating)))))
        distribution[bucket] += 1
    return {key: value for key, value in distribution.items() if value}


def get_merchant_reviews(
    merchant_id: str,
    sentiment: str | None = None,
    limit_samples: int = 5,
    db: Session | None = None,
) -> dict[str, Any]:
    session = db or SessionLocal()
    try:
        query = session.query(Review).filter(Review.merchant_id == merchant_id)
        if sentiment:
            query = query.filter(Review.sentiment == sentiment)
        rows = query.order_by(
            Review.total_like.desc().nulls_last(),
            Review.created_at.desc(),
        ).all()
        sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}
        for row in rows:
            if row.sentiment in sentiment_counts:
                sentiment_counts[row.sentiment] += 1
        bounded = rows[: max(1, min(limit_samples, 10))]
        return {
            "status": "ok",
            "merchant_id": merchant_id,
            "total_count": len(rows),
            "sentiment_counts": sentiment_counts,
            "rating_distribution": _rating_distribution(rows),
            "themes": _review_themes(rows),
            "samples": [
                {
                    "review_id": row.review_id,
                    "rating": float(row.rating) if row.rating is not None else None,
                    "sentiment": row.sentiment,
                    "text": row.text[:300],
                    "created_at": (
                        row.created_at.isoformat() if row.created_at else None
                    ),
                }
                for row in bounded
            ],
            "evidence_refs": [f"review:{row.review_id}" for row in rows],
        }
    finally:
        if db is None:
            session.close()


class GetMerchantReviewsInput(BaseModel):
    merchant_id: str
    sentiment: Literal["positive", "negative", "neutral"] | None = None
    limit_samples: int = Field(default=5, ge=1, le=10)
