"""Strict contracts for Green SM policy retrieval."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class PolicySearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=2, max_length=600)


class PolicyChunkEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    document_id: str
    title: str
    source_url: HttpUrl
    category: str
    policy_updated_at: datetime | None = None
    section_path: list[str]
    text: str
    relevance: float = Field(ge=0, le=1)


class PolicySearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "ok"
    count: int = Field(ge=0)
    results: list[PolicyChunkEvidence]
