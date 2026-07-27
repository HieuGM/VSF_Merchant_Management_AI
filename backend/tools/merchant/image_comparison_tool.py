"""Privacy-safe comparison of owner food images with public cohort images."""
from __future__ import annotations

import statistics
from typing import Any

from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import FoodImage, MenuItem, Merchant


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 3) if values else None


def _summary(rows: list[tuple[FoodImage, MenuItem | None, Merchant]]) -> dict[str, Any]:
    qualities = [
        float(image.dish_image_quality)
        for image, _, _ in rows
        if image.dish_image_quality is not None
    ]
    blur_scores = [
        float(image.blur_score)
        for image, _, _ in rows
        if image.blur_score is not None
    ]
    return {
        "image_count": len(rows),
        "quality_mean": _mean(qualities),
        "blur_mean": _mean(blur_scores),
    }


def _sample(
    row: tuple[FoodImage, MenuItem | None, Merchant],
) -> dict[str, Any]:
    image, item, merchant = row
    return {
        "image_id": image.image_id,
        "merchant_id": image.merchant_id,
        "merchant_name": merchant.name,
        "item_name": item.name if item else None,
        "url": image.url,
        "dish_image_quality": (
            round(float(image.dish_image_quality), 3)
            if image.dish_image_quality is not None
            else None
        ),
        "blur_score": (
            round(float(image.blur_score), 3)
            if image.blur_score is not None
            else None
        ),
        "evidence_ref": f"image:{image.image_id}",
    }


def compare_merchant_images(
    owner_merchant_id: str,
    competitor_merchant_ids: list[str],
    limit_per_side: int = 3,
    db: Session | None = None,
) -> dict[str, Any]:
    """Compare image-quality metadata without reading competitor-private data.

    URLs and image quality signals are part of the public marketplace surface.
    Owner samples prioritize weaker images; cohort samples prioritize strong
    public examples so the output can explain actionable visual gaps.
    """
    session = db or SessionLocal()
    try:
        owner_id = str(owner_merchant_id)
        public_ids = list(
            dict.fromkeys(
                str(item)
                for item in competitor_merchant_ids
                if item and str(item) != owner_id
            )
        )
        bounded_limit = max(1, min(int(limit_per_side), 5))

        def rows_for(ids: list[str]):
            if not ids:
                return []
            return (
                session.query(FoodImage, MenuItem, Merchant)
                .outerjoin(MenuItem, FoodImage.item_id == MenuItem.item_id)
                .join(Merchant, FoodImage.merchant_id == Merchant.merchant_id)
                .filter(
                    FoodImage.merchant_id.in_(ids),
                    Merchant.is_active == True,
                )
                .all()
            )

        owner_rows = rows_for([owner_id])
        public_rows = rows_for(public_ids)
        owner_summary = _summary(owner_rows)
        public_summary = {
            **_summary(public_rows),
            "merchant_count": len(
                {image.merchant_id for image, _, _ in public_rows}
            ),
        }

        owner_samples = [
            _sample(row)
            for row in sorted(
                owner_rows,
                key=lambda row: (
                    row[0].dish_image_quality is None,
                    float(row[0].dish_image_quality or 0),
                ),
            )[:bounded_limit]
        ]
        public_samples = [
            _sample(row)
            for row in sorted(
                public_rows,
                key=lambda row: float(row[0].dish_image_quality or -1),
                reverse=True,
            )[:bounded_limit]
        ]

        owner_quality = owner_summary["quality_mean"]
        public_quality = public_summary["quality_mean"]
        owner_blur = owner_summary["blur_mean"]
        public_blur = public_summary["blur_mean"]
        quality_delta = (
            round(owner_quality - public_quality, 3)
            if owner_quality is not None and public_quality is not None
            else None
        )
        blur_delta = (
            round(owner_blur - public_blur, 3)
            if owner_blur is not None and public_blur is not None
            else None
        )
        differences: list[str] = []
        if quality_delta is not None and quality_delta < 0:
            differences.append(
                "Điểm chất lượng ảnh trung bình của quán thấp hơn nhóm công khai."
            )
        if blur_delta is not None and blur_delta > 0:
            differences.append(
                "Ảnh của quán có độ mờ trung bình cao hơn nhóm công khai."
            )

        aggregate_refs = [
            "aggregate:image_comparison:owner_summary.quality_mean",
            "aggregate:image_comparison:public_cohort_summary.quality_mean",
        ]
        evidence_refs = aggregate_refs + [
            row["evidence_ref"] for row in owner_samples + public_samples
        ]
        return {
            "status": (
                "ok"
                if owner_rows and public_rows
                else "insufficient_data"
            ),
            "owner_merchant_id": owner_id,
            "owner_summary": owner_summary,
            "public_cohort_summary": public_summary,
            "owner_samples": owner_samples,
            "public_samples": public_samples,
            "gaps": {
                "quality_delta": quality_delta,
                "blur_delta": blur_delta,
            },
            "differences": differences,
            "evidence_refs": evidence_refs,
            "provenance": {
                "competitor_public_only": True,
                "candidate_merchant_count": len(public_ids),
            },
        }
    finally:
        if db is None:
            session.close()
