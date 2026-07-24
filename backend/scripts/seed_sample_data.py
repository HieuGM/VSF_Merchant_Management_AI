"""Seed sample data for Phase 0.5 walking skeleton (UC-04).

Idempotent script that:
- Resets tables (TRUNCATE) before seeding
- Imports ~10 sample merchants with menu items
- Uses real data from data/merchants_unique.jsonl

Usage:
    cd backend
    python scripts/seed_sample_data.py
"""
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import datetime, time
from json import loads as json_loads
from typing import Any
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from core.settings import get_settings
from database.models import Merchant, MenuItem, Review


# Sample subset: first 10 merchants from catalog
SAMPLE_SIZE = 10


def _parse_time(value: Any) -> time | None:
    """Parse 'HH:MM[:SS]' into datetime.time, else None."""
    if value is None or isinstance(value, time):
        return value
    try:
        return time.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def reset_tables(db: Session) -> None:
    """Reset tables (TRUNCATE) for idempotent seeding."""
    print("Resetting tables...")
    db.execute(text("TRUNCATE TABLE reviews CASCADE"))
    db.execute(text("TRUNCATE TABLE menu_items CASCADE"))
    db.execute(text("TRUNCATE TABLE merchants CASCADE"))
    db.commit()
    print("  Tables reset complete")


def load_sample_data() -> list[dict]:
    """Load sample merchants from data/merchants_unique.jsonl."""
    catalog_path = Path(__file__).resolve().parents[2] / "data" / "merchants_unique.jsonl"
    print(f"Loading sample data from {catalog_path}...")

    merchants = []
    with open(catalog_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= SAMPLE_SIZE:
                break
            data = json_loads(line)
            merchants.append(data)

    print(f"  Loaded {len(merchants)} merchants")
    return merchants


def seed_merchants(db: Session, merchants_data: list[dict]) -> None:
    """Seed merchants table."""
    print("Seeding merchants...")
    for m in merchants_data:
        open_hours = m.get("merchant_open_hours") or {}
        merchant = Merchant(
            merchant_id=str(m["merchant_id"]),
            name=m.get("merchant_name", m["merchant_id"]),
            cuisine=m.get("cuisine", "N/A"),
            city=m.get("city", "TP. HCM"),
            city_slug=m.get("city_slug", "tp_hcm"),
            address=m.get("merchant_address"),
            lat=m.get("merchant_lat"),
            lng=m.get("merchant_lng"),
            opens_at=_parse_time(open_hours.get("open")),
            closes_at=_parse_time(open_hours.get("close")),
            # merchant-level tags are the canonical owner (moved off menu_items)
            diet_tags=m.get("diet_tags", []),
            ingredient_tags=m.get("ingredient_tags", []),
            taste_tags=m.get("taste_tags", []),
        )
        db.add(merchant)
    db.commit()
    print(f"  Inserted {len(merchants_data)} merchants")


def seed_menu_items(db: Session, merchants_data: list[dict]) -> None:
    """Seed menu_items table (each merchant record = 1 menu item)."""
    print("Seeding menu items...")
    for m in merchants_data:
        image_url = m.get("image_url")
        item = MenuItem(
            merchant_id=str(m["merchant_id"]),
            item_id=m.get("item_id", f"{m['merchant_id']}_item_1"),
            name=m.get("name", "Menu Item"),
            category=m.get("category", "Món Việt"),
            price=m.get("price", 50000),
            description=m.get("description"),
            image_url=image_url,
            has_photo=bool(image_url),
        )
        db.add(item)
    db.commit()
    print(f"  Inserted {len(merchants_data)} menu items")


def seed_reviews(db: Session, merchants_data: list[dict]) -> None:
    """Seed sample reviews (1-2 per merchant)."""
    print("Seeding reviews...")
    review_count = 0
    for idx, m in enumerate(merchants_data):
        merchant_id_str = str(m["merchant_id"])
        # Create 1-2 sample reviews per merchant
        for i in range(1, 3 if idx % 2 == 0 else 2):
            review = Review(
                merchant_id=merchant_id_str,
                review_id=f"{merchant_id_str}_review_{i}",
                author_id=f"user_{i}",
                author_name=f"User {i}",
                rating=4.0 + (i % 2),  # 4.0 or 5.0
                text=f"Good food! Order #{i}",
                sentiment="positive",
                created_at=datetime.now(),
            )
            db.add(review)
            review_count += 1
    db.commit()
    print(f"  Inserted {review_count} reviews")


def verify_seeding(db: Session) -> None:
    """Verify seeding results."""
    print("\nVerifying seeding results:")
    merchant_count = db.scalar(text("SELECT COUNT(*) FROM merchants"))
    menu_count = db.scalar(text("SELECT COUNT(*) FROM menu_items"))
    review_count = db.scalar(text("SELECT COUNT(*) FROM reviews"))

    print(f"  Merchants: {merchant_count}")
    print(f"  Menu Items: {menu_count}")
    print(f"  Reviews: {review_count}")

    assert merchant_count == SAMPLE_SIZE, f"Expected {SAMPLE_SIZE} merchants"
    assert menu_count == SAMPLE_SIZE, f"Expected {SAMPLE_SIZE} menu items"
    assert review_count >= SAMPLE_SIZE, f"Expected at least {SAMPLE_SIZE} reviews"

    print("  [OK] All verification checks passed!")


def main() -> None:
    """Main seeding workflow."""
    print("=" * 60)
    print("Phase 0.5: Seeding sample data (UC-04 walking skeleton)")
    print("=" * 60)

    # Setup database connection
    settings = get_settings()
    engine = create_engine(str(settings.database_url))
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Step 1: Reset tables
        reset_tables(db)

        # Step 2: Load sample data
        merchants_data = load_sample_data()

        # Step 3: Seed tables
        seed_merchants(db, merchants_data)
        seed_menu_items(db, merchants_data)
        seed_reviews(db, merchants_data)

        # Step 4: Verify
        verify_seeding(db)

        print("\n[OK] Phase 0.5 seeding complete!")
        print(f"   Ready for UC-04 end-to-end test with {SAMPLE_SIZE} merchants")

    except Exception as e:
        print(f"\n[ERROR] Seeding failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
