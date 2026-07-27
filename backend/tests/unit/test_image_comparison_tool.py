from __future__ import annotations

from database.models import FoodImage, Merchant, MenuItem
from tools.merchant.image_comparison_tool import compare_merchant_images


def _seed_image(
    db_session,
    merchant_id: str,
    image_id: str,
    quality: float,
    blur: float,
) -> None:
    if db_session.get(Merchant, merchant_id) is None:
        db_session.add(
            Merchant(
                merchant_id=merchant_id,
                name=f"Merchant {merchant_id}",
                cuisine="Món Việt",
                city="Hà Nội",
                city_slug="ha-noi",
                is_active=True,
            )
        )
        db_session.flush()
    item_id = f"item-{image_id}"
    db_session.add(
        MenuItem(
            item_id=item_id,
            merchant_id=merchant_id,
            name=f"Món {image_id}",
            price=50_000,
            has_photo=True,
            is_available=True,
        )
    )
    db_session.flush()
    db_session.add(
        FoodImage(
            image_id=image_id,
            merchant_id=merchant_id,
            item_id=item_id,
            url=f"https://cdn.example.com/{image_id}.jpg",
            dish_image_quality=quality,
            blur_score=blur,
        )
    )


def test_compare_images_uses_owner_data_and_public_competitor_samples(db_session):
    _seed_image(db_session, "owner-image", "owner-low", 0.45, 0.40)
    _seed_image(db_session, "owner-image", "owner-high", 0.75, 0.10)
    _seed_image(db_session, "competitor-a", "competitor-best", 0.90, 0.05)
    _seed_image(db_session, "competitor-b", "competitor-good", 0.80, 0.10)
    db_session.commit()

    result = compare_merchant_images(
        owner_merchant_id="owner-image",
        competitor_merchant_ids=[
            "owner-image",
            "competitor-a",
            "competitor-b",
        ],
        limit_per_side=2,
        db=db_session,
    )

    assert result["status"] == "ok"
    assert result["owner_summary"]["image_count"] == 2
    assert result["public_cohort_summary"]["merchant_count"] == 2
    assert {row["merchant_id"] for row in result["public_samples"]} == {
        "competitor-a",
        "competitor-b",
    }
    assert result["gaps"]["quality_delta"] == -0.25
    assert result["gaps"]["blur_delta"] == 0.175
    assert all(ref.startswith(("image:", "aggregate:")) for ref in result["evidence_refs"])
    assert "operation_kpis" not in str(result)
    assert "complaints" not in str(result)


def test_compare_images_reports_insufficient_data_without_public_comparison(
    db_session,
):
    _seed_image(db_session, "owner-only-image", "owner-only", 0.7, 0.1)
    db_session.commit()

    result = compare_merchant_images(
        owner_merchant_id="owner-only-image",
        competitor_merchant_ids=[],
        db=db_session,
    )

    assert result["status"] == "insufficient_data"
    assert result["public_samples"] == []
