"""Typed contracts for merchant-owner query planning and execution."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class Capability(str, Enum):
    RESTAURANT_SEARCH = "restaurant_search"
    MARKET_COHORT_ANALYSIS = "market_cohort_analysis"
    OWNER_PROFILE_ANALYSIS = "owner_profile_analysis"
    OWNER_REVIEW_ANALYSIS = "owner_review_analysis"
    OWNER_DIAGNOSIS = "owner_diagnosis"
    OWNER_VS_MARKET_BENCHMARK = "owner_vs_market_benchmark"
    RECOMMENDATION = "recommendation"
    IMAGE_COMPARISON = "image_comparison"
    GENERAL_CHAT = "general_chat"


CAPABILITY_ORDER: tuple[Capability, ...] = (
    Capability.RESTAURANT_SEARCH,
    Capability.MARKET_COHORT_ANALYSIS,
    Capability.OWNER_PROFILE_ANALYSIS,
    Capability.OWNER_REVIEW_ANALYSIS,
    Capability.OWNER_DIAGNOSIS,
    Capability.OWNER_VS_MARKET_BENCHMARK,
    Capability.RECOMMENDATION,
    Capability.IMAGE_COMPARISON,
    Capability.GENERAL_CHAT,
)


class TokenUsage(BaseModel):
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            total_tokens=self.total_tokens + other.total_tokens,
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
        )


class MerchantExecutionContext(BaseModel):
    trace_id: str
    session_id: str
    owner_merchant_id: str
    user_id: str | None = None


class SearchFilters(BaseModel):
    query: str | None = None
    city: str | None = None
    district: str | None = None
    cuisine: str | None = None
    category: str | None = None
    price_level: str | None = None
    min_menu_price: int | None = Field(default=None, ge=0)
    max_menu_price: int | None = Field(default=None, ge=0)
    min_rating: float | None = Field(default=None, ge=0, le=10)
    radius_km: float | None = Field(default=None, ge=0.5, le=20)
    use_owner_location: bool = False
    limit: int = Field(default=10, ge=1, le=25)


class CapabilityPlan(BaseModel):
    capabilities: list[Capability]
    filters: SearchFilters = Field(default_factory=SearchFilters)
    requested_dimensions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_capabilities(self) -> "CapabilityPlan":
        selected = set(self.capabilities)
        if selected.intersection(
            {
                Capability.OWNER_DIAGNOSIS,
                Capability.RECOMMENDATION,
            }
        ):
            selected.add(Capability.OWNER_PROFILE_ANALYSIS)
        if Capability.RECOMMENDATION in selected:
            selected.add(Capability.OWNER_DIAGNOSIS)
        if Capability.OWNER_VS_MARKET_BENCHMARK in selected:
            selected.update(
                {
                    Capability.RESTAURANT_SEARCH,
                    Capability.MARKET_COHORT_ANALYSIS,
                }
            )
        if Capability.MARKET_COHORT_ANALYSIS in selected:
            selected.add(Capability.RESTAURANT_SEARCH)
        if Capability.IMAGE_COMPARISON in selected:
            selected.update(
                {
                    Capability.RESTAURANT_SEARCH,
                    Capability.MARKET_COHORT_ANALYSIS,
                    Capability.OWNER_PROFILE_ANALYSIS,
                    Capability.OWNER_VS_MARKET_BENCHMARK,
                }
            )
        if len(selected) > 1:
            selected.discard(Capability.GENERAL_CHAT)
        if not selected:
            selected.add(Capability.GENERAL_CHAT)
        self.capabilities = [cap for cap in CAPABILITY_ORDER if cap in selected]
        return self


class PlannerResult(BaseModel):
    rewritten_query: str
    plan: CapabilityPlan
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    used_fallback: bool = False


class ExecutionStep(BaseModel):
    step_id: str
    agent_name: str
    tool_name: str
    depends_on: list[str] = Field(default_factory=list)
    owner_private: bool = False


class CitedNumber(BaseModel):
    value: float
    evidence_ref: str
    field: str


class EvidenceClaim(BaseModel):
    claim: str
    dimension: str | None = None
    evidence_refs: list[str]
    numbers: list[CitedNumber] = Field(default_factory=list)


class RejectedClaim(BaseModel):
    claim: EvidenceClaim
    reason: str
    evidence_ref: str | None = None


class EvidenceValidationResult(BaseModel):
    status: str
    valid_claims: list[EvidenceClaim] = Field(default_factory=list)
    rejected: list[RejectedClaim] = Field(default_factory=list)
    resolved_evidence: dict[str, dict] = Field(default_factory=dict)


class ExecutionResult(BaseModel):
    outputs: dict[str, dict] = Field(default_factory=dict)
    merchants: list[dict] = Field(default_factory=list)
    claims: list[EvidenceClaim] = Field(default_factory=list)
    aggregate_snapshots: dict[str, dict] = Field(default_factory=dict)
    trace_steps: list[dict] = Field(default_factory=list)
