"""Base API contracts — envelope, paging, health (design §11).

FROZEN SEAM: both verticals import these base shapes. Domain-specific models live in
profile.py / agent.py / preference.py / events.py. Change only via contract protocol.
"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None


class ErrorEnvelope(BaseModel):
    """§11.10 error envelope."""

    error: ErrorBody


class Page(BaseModel, Generic[T]):
    """Generic paginated list."""

    items: list[T]
    total: int
    query_id: str | None = None


class HealthResponse(BaseModel):
    status: str
    database: str
    redis: str
    llm_configured: bool


class Location(BaseModel):
    lat: float
    lng: float
    accuracy_m: float | None = None
