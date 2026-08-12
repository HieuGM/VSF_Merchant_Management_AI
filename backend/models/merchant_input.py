"""Strict contracts between request preparation and routing."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ProposedOutcome = Literal["fast_answer", "coordinate"]
RouteOutcome = Literal[
    "reject",
    "fast_answer",
    "coordinate",
]


class ResolvedReference(BaseModel):
    """A context-derived entity reference, with explicit confidence."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["public_merchant", "owner_merchant", "menu_item", "location"]
    merchant_id: str | None = None
    name: str | None = None
    source: str = Field(min_length=1)
    confidence: Literal["high", "low"]


class PreparedRequest(BaseModel):
    """Tool-less input-layer output; deliberately excludes planning fields."""

    model_config = ConfigDict(extra="forbid")

    rewritten_query: str = Field(min_length=1, max_length=1200)
    resolved_references: list[ResolvedReference] = Field(
        default_factory=list,
        max_length=5,
    )
    scope_candidate: Literal["allowed", "out_of_scope", "unclear"]
    missing_context: list[str] = Field(default_factory=list, max_length=5)
    proposed_outcome: ProposedOutcome


class PromptBudget(BaseModel):
    """Explicit per-prompt dynamic-input and generated-output bounds."""

    model_config = ConfigDict(extra="forbid")

    dynamic_input_limit: int = Field(gt=0)
    output_limit: int = Field(gt=0)
