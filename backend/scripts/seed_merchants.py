"""Seed merchants table with sample data for Phase 0.5 walking skeleton.

Populates basic merchant records to enable UC-04 search testing.

Business hours use the typed `opens_at` / `closes_at` columns (single daily
schedule; the legacy weekday `open_hours` JSON column was dropped in migration
c2d3e4f5a6b7). `is_demo_target` is a boolean.
"""
from __future__ import annotations

import sys
from datetime import time
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.connection import SessionLocal
from database.models import Merchant


def seed_merchants() -> None:
    """Seed merchants table with sample restaurant data."""
    db = SessionLocal()
    try:
        # Check if already seeded
        existing = db.query(Merchant).count()
        if existing > 0:
            print(f"[OK] Merchants table already has {existing} records")
            return

        # Sample merchant data (Saigon area)
        merchants = [
            Merchant(
                merchant_id="m001", name="Phở Le", cuisine="Vietnamese",
                address="123 Nguyễn Huệ, Quận 1", lat=10.7797, lng=106.6988,
                opens_at=time(7, 0), closes_at=time(22, 0),
                city="Ho Chi Minh City", city_slug="ho-chi-minh-city",
                source="demo", is_demo_target=True,
            ),
            Merchant(
                merchant_id="m002", name="Sushi Takashi", cuisine="Japanese",
                address="456 Lê Lợi, Quận 3", lat=10.7812, lng=106.6911,
                opens_at=time(11, 0), closes_at=time(22, 0),
                city="Ho Chi Minh City", city_slug="ho-chi-minh-city",
                source="demo", is_demo_target=True,
            ),
            Merchant(
                merchant_id="m003", name="Pizza Napoli", cuisine="Italian",
                address="789 Hai Bà Trưng, Quận 1", lat=10.7768, lng=106.7055,
                opens_at=time(10, 0), closes_at=time(22, 0),
                city="Ho Chi Minh City", city_slug="ho-chi-minh-city",
                source="demo", is_demo_target=True,
            ),
            Merchant(
                merchant_id="m004", name="Bánh Mì Huỳnh Hoa", cuisine="Vietnamese",
                address="321 Lê Duẩn, Quận 1", lat=10.7825, lng=106.7024,
                opens_at=time(6, 0), closes_at=time(20, 0),
                city="Ho Chi Minh City", city_slug="ho-chi-minh-city",
                source="demo", is_demo_target=True,
            ),
            Merchant(
                merchant_id="m005", name="Com Nieu Gateway", cuisine="Vietnamese",
                address="55 Thủ Đức, Quận Thủ Đức", lat=10.8754, lng=106.7521,
                opens_at=time(10, 0), closes_at=time(21, 0),
                city="Ho Chi Minh City", city_slug="ho-chi-minh-city",
                source="demo", is_demo_target=True,
            ),
        ]

        # Add all merchants
        db.add_all(merchants)
        db.commit()

        print(f"[OK] Seeded {len(merchants)} merchants")

        # Verify
        count = db.query(Merchant).count()
        print(f"[OK] Total merchants in database: {count}")

    except Exception as e:
        print(f"[ERROR] Error seeding merchants: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_merchants()
