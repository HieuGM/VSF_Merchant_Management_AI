"""Customer Crew task output contracts (Phase 04/05).

Structured `output_pydantic` targets for each Customer Discovery task. Final crew output
maps to `models.agent.CustomerChatResponse`. Reuses `ProfileDeltaSuggestion`
(models/preference.py) so proposal shape stays single-sourced.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from models.preference import ProfileDeltaSuggestion


class MerchantCandidate(BaseModel):
    """A single ranked merchant in a search result."""

    merchant_id: str
    name: str
    cuisine: str | None = None
    address: str | None = None
    distance_km: float | None = None
    avg_rating: float | None = None
    match_score: float = 0.0


class SearchTaskOutput(BaseModel):
    """Output of `search_task` (restaurant_search agent)."""

    candidates: list[MerchantCandidate] = Field(default_factory=list)
    applied_filters: dict[str, Any] = Field(default_factory=dict)
    count: int = 0


class PreferenceTaskOutput(BaseModel):
    """Output of `preference_task` (preference_reasoning agent) — proposals only."""

    suggestions: list[ProfileDeltaSuggestion] = Field(default_factory=list)
    weather_summary: str | None = None
    reasoning: str | None = None


class ExplanationTaskOutput(BaseModel):
    """Output of `explanation_task` (customer_explanation agent)."""

    answer: str
    reasons: list[str] = Field(default_factory=list)
    referenced_signals: list[str] = Field(default_factory=list)
