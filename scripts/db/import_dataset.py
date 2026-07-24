"""Import du lieu da chuan bi vao Postgres.

Aligned with docs/2026-07-23-merchant-relational-schema-design.md.
All merchant-domain tables are now relational — no dimensions_json.

- --dry-run : chi build row + dem, KHONG dung DB (kiem chung mapping).
- (mac dinh): tao bang neu chua co, TRUNCATE, roi bulk insert.
- --core-only: bo qua menu_items + food_images (2 bang nang), chi core tables.

Chay: cd backend && python ../scripts/db/import_dataset.py --dry-run
Can Postgres chay + .env (POSTGRES_*/DB_*).
"""
import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

import build_import_rows as builder

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")  # nap creds DB truoc khi import database.connection
sys.path.insert(0, str(ROOT / "backend"))  # de import database.* cua teammate

# Insert order: parent tables first, children after.
# Truncate order is reversed automatically.
INSERT_ORDER = [
    "merchants",
    "operational_metrics",
    "merchant_profiles",
    "merchant_ratings",
    "reviews",                           # before complaints (FK)
    "delivery_feedbacks",
    "merchant_dimension_calculations",
    "merchant_dimension_evidence",
    "merchant_complaints",
    "menu_items",
    "food_images",
]


def build_all(core_only):
    cat = builder._catalog_map()
    rows = builder.build_from_profiles(cat)
    valid_ids = {m["merchant_id"] for m in rows["merchants"]}
    if not core_only:
        rows.update(builder.build_menu_and_images(cat, valid_ids))
    else:
        rows["menu_items"] = []
        rows["food_images"] = []
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--core-only", action="store_true")
    ap.add_argument("--chunk", type=int, default=2000)
    args = ap.parse_args()

    print("building rows from prepared data ...")
    rows = build_all(args.core_only)
    print("\nrow counts per table:")
    for t in INSERT_ORDER:
        print(f"  {t:40} {len(rows.get(t, [])):>7}")

    if args.dry_run:
        # in vai sample de kiem tra mapping
        print("\nsample merchant:", rows["merchants"][0])
        if rows["reviews"]:
            print("sample review:", rows["reviews"][0])
        if rows.get("merchant_dimension_calculations"):
            print("sample calculation:", rows["merchant_dimension_calculations"][0])
        if rows.get("merchant_dimension_evidence"):
            print("sample evidence:", rows["merchant_dimension_evidence"][0])
        if rows.get("merchant_complaints"):
            print("sample complaint:", rows["merchant_complaints"][0])
        if rows["menu_items"]:
            print("sample menu_item:", rows["menu_items"][0])
        print("\nDRY-RUN ok — khong ghi DB.")
        return

    # === ghi that vao DB ===
    from database.connection import engine, SessionLocal, Base
    from database import models  # noqa: F401 - dang ky bang vao Base.metadata
    from sqlalchemy import text

    model_map = {
        "merchants": models.Merchant,
        "operational_metrics": models.OperationalMetric,
        "merchant_profiles": models.MerchantProfile,
        "merchant_ratings": models.MerchantRating,
        "merchant_dimension_calculations": models.MerchantDimensionCalculation,
        "merchant_dimension_evidence": models.MerchantDimensionEvidence,
        "merchant_complaints": models.MerchantComplaint,
        "reviews": models.Review,
        "delivery_feedbacks": models.DeliveryFeedback,
        "menu_items": models.MenuItem,
        "food_images": models.FoodImage,
    }

    print("\ncreating tables if not exist ...")
    Base.metadata.create_all(engine)

    db = SessionLocal()
    try:
        tables = [t for t in INSERT_ORDER if rows.get(t)]
        print("truncating:", ", ".join(tables))
        db.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
        db.commit()
        for t in INSERT_ORDER:
            data = rows.get(t, [])
            if not data:
                continue
            for i in range(0, len(data), args.chunk):
                db.bulk_insert_mappings(model_map[t], data[i:i + args.chunk])
                db.commit()
            print(f"  inserted {len(data):>7} -> {t}")
        print("\nIMPORT DONE.")
    except Exception as e:
        db.rollback()
        print(f"\nIMPORT FAILED: {type(e).__name__}: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
