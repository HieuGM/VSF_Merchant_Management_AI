"""Contract tests for the current-state relational merchant schema."""

from database.models import (
    MarketTrendingDish,
    Merchant,
    MerchantComplaint,
    MerchantDimensionCalculation,
    MerchantDimensionEvidence,
    MerchantProfile,
    MerchantRating,
    OperationalMetric,
)


def test_profile_uses_typed_scores_without_legacy_json_columns():
    columns = MerchantProfile.__table__.columns

    expected_scores = {
        "food_quality_score",
        "image_quality_score",
        "delivery_quality_score",
        "packaging_score",
        "service_score",
        "waiting_time_score",
        "menu_diversity_score",
        "price_competitiveness_score",
    }
    assert expected_scores.issubset(columns.keys())
    assert "overall_score_internal" in columns
    assert "dimensions_json" not in columns
    assert "profile_json" not in columns


def test_filterable_merchant_and_operation_attributes_are_typed_columns():
    merchant_columns = Merchant.__table__.columns
    operation_columns = OperationalMetric.__table__.columns

    for name in (
        "opens_at",
        "closes_at",
        "taste_tags",
        "diet_tags",
        "ingredient_tags",
        "customer_segments",
        "is_active",
    ):
        assert name in merchant_columns

    for name in (
        "cancel_rate",
        "acceptance_rate",
        "estimated_daily_orders",
        "avg_delivery_time_min",
        "on_time_rate",
        "driver_rating",
        "packaging_ok_rate",
    ):
        assert name in operation_columns


def test_relational_profile_support_tables_are_declared():
    assert MerchantRating.__tablename__ == "merchant_ratings"
    assert (
        MerchantDimensionCalculation.__tablename__
        == "merchant_dimension_calculations"
    )
    assert MerchantDimensionEvidence.__tablename__ == "merchant_dimension_evidence"
    assert MerchantComplaint.__tablename__ == "merchant_complaints"
    assert MarketTrendingDish.__tablename__ == "market_trending_dishes"


def test_no_persisted_competitor_or_distance_model_exists():
    table_names = set(Merchant.metadata.tables)

    assert "merchant_competitors" not in table_names
    for table in Merchant.metadata.tables.values():
        assert "distance_km" not in table.columns
