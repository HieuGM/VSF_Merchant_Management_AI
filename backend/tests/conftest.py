"""Shared pytest fixtures — runs WITHOUT Docker (A-04).

The DB dependency is overridden with a stub so the app boots and /health responds
without Postgres; the cache uses the in-memory adapter by default.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from core.dependencies import get_db_session

from crewai import LLM


class FakeLLM(LLM):
    """A CrewAI LLM stand-in that never builds a network client (bypasses __new__).

    Lets crew/agent tests run with no NVIDIA NIM key and no network. Carries a `model`
    so per-agent tier assertions still work."""

    def __new__(cls, *args, **kwargs):  # skip crewai.LLM native-provider init
        return object.__new__(cls)

    def __init__(self, model: str = "openai/fake-model") -> None:
        self.model = model
        self.stop = []
        self.temperature = None


@pytest.fixture
def fake_llm_fpt() -> "FakeLLM":
    """Fake FPT DeepSeek LLM for all customer specialists (no network/key needed)."""
    return FakeLLM("openai/DeepSeek-V4-Flash")


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
