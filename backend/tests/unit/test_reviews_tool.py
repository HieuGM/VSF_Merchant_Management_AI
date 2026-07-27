from __future__ import annotations

from datetime import datetime, timezone

from database.models import Merchant, Review
from tools.merchant.reviews_tool import get_merchant_reviews


def test_get_merchant_reviews_aggregates_sentiment_themes_and_evidence(db_session):
    merchant = Merchant(
        merchant_id="m_reviews_01",
        name="Quán Review Test",
        cuisine="Món Việt",
        city="Hà Nội",
        city_slug="ha_noi",
    )
    db_session.add(merchant)
    db_session.add_all(
        [
            Review(
                review_id="rv_review_01",
                merchant_id=merchant.merchant_id,
                rating=4,
                text="Món ngon nhưng giao hàng hơi chậm",
                sentiment="positive",
                source_kind="development_fixture",
                created_at=datetime.now(timezone.utc),
            ),
            Review(
                review_id="rv_review_02",
                merchant_id=merchant.merchant_id,
                rating=2,
                text="Đóng gói kém và món bị nguội",
                sentiment="negative",
                source_kind="development_fixture",
                created_at=datetime.now(timezone.utc),
            ),
        ]
    )
    db_session.commit()

    result = get_merchant_reviews(merchant.merchant_id, db=db_session)

    assert result["status"] == "ok"
    assert result["total_count"] == 2
    assert result["sentiment_counts"] == {
        "positive": 1,
        "negative": 1,
        "neutral": 0,
    }
    assert result["themes"]["delivery"] == 1
    assert result["themes"]["packaging"] == 1
    assert set(result["evidence_refs"]) == {
        "review:rv_review_01",
        "review:rv_review_02",
    }


def test_get_merchant_reviews_filters_sentiment(db_session):
    merchant = Merchant(
        merchant_id="m_reviews_02",
        name="Quán Review Filter",
        cuisine="Món Việt",
        city="Hà Nội",
        city_slug="ha_noi",
    )
    db_session.add(merchant)
    for index, sentiment in enumerate(("positive", "negative")):
        db_session.add(
            Review(
                review_id=f"rv_filter_{index}",
                merchant_id=merchant.merchant_id,
                rating=5 if sentiment == "positive" else 1,
                text=f"Review {sentiment}",
                sentiment=sentiment,
                source_kind="development_fixture",
                created_at=datetime.now(timezone.utc),
            )
        )
    db_session.commit()

    result = get_merchant_reviews(
        merchant.merchant_id,
        sentiment="negative",
        db=db_session,
    )

    assert result["total_count"] == 1
    assert result["samples"][0]["sentiment"] == "negative"
