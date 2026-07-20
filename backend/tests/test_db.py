import os
import sys
from pathlib import Path
from sqlalchemy import inspect, text

# Add backend to path to allow direct execution
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.connection import engine, SessionLocal
from database.models import Base

def test_db_connection():
    """Verify that we can establish a connection to the PostgreSQL database."""
    print("Testing connection to PostgreSQL...")
    try:
        session = SessionLocal()
        # Execute simple query to test connection
        result = session.execute(text("SELECT 1;")).scalar()
        assert result == 1
        print("Successfully connected to the database!")
    except Exception as e:
        print(f"Database connection failed: {e}")
        raise e
    finally:
        session.close()

def test_schema_tables():
    """Verify that all required schema tables exist in the database."""
    print("Verifying schema tables...")
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
        "chat_messages"
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
