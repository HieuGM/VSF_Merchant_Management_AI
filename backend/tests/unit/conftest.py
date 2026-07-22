"""Unit test conftest for Dev B using real PostgreSQL connection from database.connection."""
import sys
from unittest.mock import MagicMock
import pytest
from database.connection import engine, SessionLocal


# Mock Dev A's missing uncommitted modules in sys.modules for test runner
if "flows.customer_flow" not in sys.modules:
    sys.modules["flows.customer_flow"] = MagicMock()

if "tools.customer.merchant_tools" not in sys.modules:
    sys.modules["tools.customer.merchant_tools"] = MagicMock()


@pytest.fixture
def db_session():
    """PostgreSQL session fixture for repository unit tests (uses transactional rollback)."""
    connection = engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()
