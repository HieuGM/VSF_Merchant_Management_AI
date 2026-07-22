import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

# Add backend to path to allow direct execution
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.connection import engine, SessionLocal
from database.models import Base


def _require_db():
    """Skip integration tests when Postgres is unreachable (A-04: suite runs w/o Docker)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
    except OperationalError as exc:  # noqa: F841
        pytest.skip("Postgres not reachable — integration test skipped (no Docker).")


def test_db_connection():
    """Verify that we can establish a connection to the PostgreSQL database."""
    _require_db()
    session = SessionLocal()
    try:
        result = session.execute(text("SELECT 1;")).scalar()
        assert result == 1
    finally:
        session.close()

def test_schema_tables():
    """Verify that all required schema tables exist in the database."""
    _require_db()
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    expected_tables = {
        "merchants",
        "menu_items",
        "reviews",
        "delivery_feedbacks",
        "food_images",
        "operational_metrics",
        "merchant_profiles",
        "user_profiles",
        "chat_sessions",
        "chat_messages",
        # §6.2 runtime records
        "preference_events",
        "interaction_events",
        "agent_runs",
        "agent_events",
    }
    
    print(f"Existing tables in database: {existing_tables}")
    missing_tables = expected_tables - set(existing_tables)
    
    assert not missing_tables, f"Missing tables in database: {missing_tables}"
    print("All expected tables exist in the database schema!")

if __name__ == "__main__":
    # If run directly as a script
    try:
        test_db_connection()
        test_schema_tables()
        print("\nAll database integration tests PASSED!")
        sys.exit(0)
    except Exception as e:
        print(f"\nDatabase integration tests FAILED: {e}")
        sys.exit(1)
