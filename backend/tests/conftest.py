"""Shared pytest fixtures (A-04).

Provides client fixture for API stubs and db_session fixture for DB tests.
Mocks uncommitted Dev A modules so the test runner boots cleanly.
"""
import sys
from unittest.mock import MagicMock

# Mock uncommitted Dev A modules in test runner
if "flows.customer_flow" not in sys.modules:
    mock_flow = MagicMock()
    mock_flow.customer_flow.search_restaurants.return_value = {
        "trace_id": "tr-mock-123",
        "results": {
            "merchants": [],
            "total": 0,
            "filters_applied": {},
        },
    }
    sys.modules["flows.customer_flow"] = mock_flow

if "tools.customer.merchant_tools" not in sys.modules:
    sys.modules["tools.customer.merchant_tools"] = MagicMock()

import pytest
from fastapi.testclient import TestClient
from app.main import app
import app.main as app_main
from core.dependencies import get_db_session
from database.connection import engine, SessionLocal


class _StubResult:
    """Stub result returned by _StubSession.execute()."""

    def scalar_one_or_none(self):
        return None

    def scalar(self):
        return None

    def scalars(self):
        return self

    def all(self):
        return []

    def first(self):
        return None


class _StubSession:
    """Minimal stand-in that satisfies health's `db.execute` and stub routes."""

    def execute(self, *_args, **_kwargs):  # noqa: ANN002, ANN003
        return _StubResult()

    def get(self, entity, ident):
        return None

    def query(self, entity):
        mock_q = MagicMock()
        mock_q.filter.return_value.order_by.return_value.all.return_value = []
        return mock_q

    def close(self) -> None:  # pragma: no cover
        pass


def _override_db():
    yield _StubSession()


@pytest.fixture
def client() -> TestClient:
    langfuse = MagicMock()
    original_initialize = app_main.initialize_langfuse
    app_main.initialize_langfuse = lambda: langfuse
    app.dependency_overrides[get_db_session] = _override_db
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        app_main.initialize_langfuse = original_initialize


@pytest.fixture
def db_session():
    """PostgreSQL session fixture for unit & contract tests (uses transactional rollback)."""
    connection = engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()
