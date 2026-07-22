"""Shared pytest fixtures — runs WITHOUT Docker (A-04).

The DB dependency is overridden with a stub so the app boots and /health responds
without Postgres; the cache uses the in-memory adapter by default.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from core.dependencies import get_db_session


class _StubSession:
    """Minimal stand-in that satisfies health's `db.execute(text("SELECT 1"))`."""

    def execute(self, *_args, **_kwargs):  # noqa: ANN002, ANN003
        return None

    def close(self) -> None:  # pragma: no cover
        pass


def _override_db():
    yield _StubSession()


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[get_db_session] = _override_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
