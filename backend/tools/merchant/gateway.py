"""Run-scoped, policy-controlled CrewAI tools for Merchant Advisor agents."""
from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Literal, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from core.cache import CachePort
from models.merchant_agentic import (
    AgenticRunContext,
    normalize_city_slugs,
    normalize_text,
)
from models.policy_rag import PolicySearchInput
from services.policy_rag_service import PolicyRagService
from services.request_telemetry import SqlQueryMonitor
from services.merchant_trace_collector import (
    GatewayToolInvocation,
    ToolCorrelationBridge,
    TraceCollector,
    sanitize_developer_trace,
)
from services.merchant_data_policy import MerchantDataPolicy, PUBLIC_DIMENSIONS
from tools.merchant.profile_tool import (
    GetMerchantProfileSummaryInput,
    get_merchant_profile_summary,
)
from tools.merchant.metrics_tool import (
    GetMerchantOperationalMetricsInput,
    get_merchant_operational_metrics,
)
from tools.merchant.reviews_tool import GetMerchantReviewsInput, get_merchant_reviews
from tools.merchant.complaints_tool import (
    GetMerchantComplaintsInput,
    get_merchant_complaints,
)
from tools.merchant.menu_image_tool import (
    GetMenuAndFoodImagesInput,
    get_menu_and_food_images,
)
from tools.merchant.image_comparison_tool import compare_merchant_images
from tools.merchant.competitor_tool import (
    CompareMerchantBenchmarkInput,
    compare_merchant_benchmark,
)
from tools.merchant.cohort_tool import (
    CompareOwnerToPublicCohortInput,
    aggregate_public_merchant_cohort,
    compare_owner_to_public_cohort,
)
from tools.merchant.diagnosis_tool import diagnose_merchant, recommend_improvements
from tools.merchant.search_tool import SearchMerchantsInput, search_merchants
from tools.merchant.public_detail_tool import get_public_merchant_detail


class _GatewayTool(BaseTool):
    """Common CrewAI tool base retaining only run-local gateway state."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    gateway: Any = Field(exclude=True)
    agent_name: str

    def _invoke(self, kwargs: dict[str, Any], operation: Callable[[], str]) -> str:
        with self.gateway.trace_tool_invocation(self.agent_name, self.name, kwargs):
            return operation()


class GatewaySearchMerchantsTool(_GatewayTool):
    name: str = "search_merchants"
    description: str = (
        "Search public merchants using explicit filters. City accepts a city name "
        "or canonical snake-case city_slug; the gateway canonicalizes it before "
        "cache and database lookup."
    )
    args_schema: Type[BaseModel] = SearchMerchantsInput

    def _run(self, **kwargs: Any) -> str:
        return self._invoke(kwargs, lambda: self.gateway.run_market_search(**kwargs))


class PublicMerchantDetailInput(BaseModel):
    merchant_id: str = Field(description="Public merchant ID from search results or conversation state.")
    menu_limit: int = Field(default=20, ge=1, le=50)


class GatewayPublicMerchantDetailTool(_GatewayTool):
    name: str = "get_public_merchant_detail"
    description: str = (
        "Retrieve public merchant details by ID, including opening hours, address, "
        "coordinates, ratings, and available menu items. Use for menu/hour follow-ups."
    )
    args_schema: Type[BaseModel] = PublicMerchantDetailInput

    def _run(self, **kwargs: Any) -> str:
        return self._invoke(kwargs, lambda: self.gateway.run_public_detail(**kwargs))


class OwnerBoundInput(BaseModel):
    """Empty schema for operations whose merchant target is the chat owner."""


class OwnerProfileInput(BaseModel):
    """Owner-scoped profile filters; identity is never an LLM argument."""

    dimensions: list[
        Literal[
            "food_quality",
            "image_quality",
            "delivery_quality",
            "packaging",
            "service",
            "waiting_time",
            "menu_diversity",
            "price_competitiveness",
        ]
    ] | None = None


class OwnerMetricsInput(BaseModel):
    """Metrics have no owner-supplied filters."""


class OwnerReviewsInput(BaseModel):
    """Optional bounded filters for the current owner's reviews."""

    sentiment: Literal["positive", "negative", "neutral"] | None = None
    limit_samples: int = Field(default=5, ge=1, le=10)


class OwnerComplaintsInput(BaseModel):
    """Optional bounded filters for the current owner's complaints."""

    category: str | None = None
    severity: Literal["low", "medium", "high"] | None = None
    limit_samples: int = Field(default=3, ge=1, le=5)


class OwnerMenuInput(BaseModel):
    """Optional bounded filters for the current owner's menu/image metadata."""

    only_with_images: bool = False
    min_image_quality: float | None = None
    category: str | None = None
    limit: int = Field(default=10, ge=1, le=20)


class OwnerBenchmarkInput(BaseModel):
    """Public comparison filters; gateway supplies the owner target."""

    radius_km: float = Field(default=5.0, ge=0.5, le=20.0)
    limit: int = Field(default=5, ge=1, le=10)
    cuisine: str | None = None
    category: str | None = None
    dimensions: list[
        Literal[
            "food_quality",
            "image_quality",
            "delivery_quality",
            "packaging",
            "service",
            "waiting_time",
            "menu_diversity",
            "price_competitiveness",
        ]
    ] | None = None


class OwnerImageComparisonInput(BaseModel):
    """Public cohort input for comparing the current owner's food images."""

    search_ref: str | None = Field(
        default=None,
        description="Run-scoped public cohort reference returned by search_merchants.",
    )
    competitor_merchant_ids: list[str] | None = Field(
        default=None,
        description="Public merchant IDs when no search_ref is available.",
    )
    limit_per_side: int = Field(default=3, ge=1, le=5)


class GatewayAggregateCohortInput(BaseModel):
    """Gateway-only aggregate input that can resolve a run-scoped search ref."""

    merchant_ids: list[str] | None = None
    search_ref: str | None = Field(
        default=None,
        description="Run-scoped cohort reference returned by search_merchants.",
    )
    step_id: str


class GatewayOwnerProfileTool(_GatewayTool):
    name: str = "get_owner_profile_summary"
    description: str = (
        "Retrieve the current merchant owner's quality profile. The owner target "
        "is bound by the current run and cannot be changed by tool arguments."
    )
    args_schema: Type[BaseModel] = OwnerProfileInput

    def _run(self, **kwargs: Any) -> str:
        return self._invoke(
            kwargs,
            lambda: self.gateway.run_owner_operation("profile", **kwargs),
        )


class GatewayOwnerMetricsTool(_GatewayTool):
    name: str = "get_owner_operational_metrics"
    description: str = "Retrieve the current owner's operational metrics."
    args_schema: Type[BaseModel] = OwnerMetricsInput

    def _run(self, **kwargs: Any) -> str:
        return self._invoke(kwargs, lambda: self.gateway.run_owner_operation("metrics", **kwargs))


class GatewayOwnerReviewsTool(_GatewayTool):
    name: str = "get_owner_reviews"
    description: str = "Retrieve the current owner's review aggregates and bounded samples."
    args_schema: Type[BaseModel] = OwnerReviewsInput

    def _run(self, **kwargs: Any) -> str:
        return self._invoke(kwargs, lambda: self.gateway.run_owner_operation("reviews", **kwargs))


class GatewayOwnerComplaintsTool(_GatewayTool):
    name: str = "get_owner_complaints"
    description: str = "Retrieve the current owner's private complaint aggregates."
    args_schema: Type[BaseModel] = OwnerComplaintsInput

    def _run(self, **kwargs: Any) -> str:
        return self._invoke(kwargs, lambda: self.gateway.run_owner_operation("complaints", **kwargs))


class GatewayOwnerMenuTool(_GatewayTool):
    name: str = "get_owner_menu_and_food_images"
    description: str = "Retrieve the current owner's menu and food image metadata."
    args_schema: Type[BaseModel] = OwnerMenuInput

    def _run(self, **kwargs: Any) -> str:
        return self._invoke(kwargs, lambda: self.gateway.run_owner_operation("menu", **kwargs))


class GatewayOwnerImageComparisonTool(_GatewayTool):
    name: str = "compare_merchant_images"
    description: str = (
        "Compare current-owner food image metadata with public cohort images. "
        "Use a search_ref from search_merchants whenever available."
    )
    args_schema: Type[BaseModel] = OwnerImageComparisonInput

    def _run(self, **kwargs: Any) -> str:
        return self._invoke(kwargs, lambda: self.gateway.run_owner_image_comparison(**kwargs))


class GatewayOwnerDiagnosisTool(_GatewayTool):
    name: str = "diagnose_owner_merchant"
    description: str = "Generate evidence-backed diagnosis for the current owner only."
    args_schema: Type[BaseModel] = OwnerBoundInput

    def _run(self, **kwargs: Any) -> str:
        return self._invoke(kwargs, lambda: self.gateway.run_owner_operation("diagnosis", **kwargs))


class GatewayOwnerRecommendationTool(_GatewayTool):
    name: str = "recommend_owner_improvements"
    description: str = "Generate evidence-backed improvement actions for the current owner only."
    args_schema: Type[BaseModel] = OwnerBoundInput

    def _run(self, **kwargs: Any) -> str:
        return self._invoke(kwargs, lambda: self.gateway.run_owner_operation("recommendation", **kwargs))


class GatewayOwnerBenchmarkTool(_GatewayTool):
    name: str = "compare_owner_to_nearby_public_merchants"
    description: str = (
        "Compare the current owner with nearby public merchants. Radius, cuisine, "
        "and category must be explicit when required by the question."
    )
    args_schema: Type[BaseModel] = OwnerBenchmarkInput

    def _run(self, **kwargs: Any) -> str:
        return self._invoke(kwargs, lambda: self.gateway.run_owner_operation("benchmark", **kwargs))


class GatewayAggregateCohortTool(_GatewayTool):
    name: str = "aggregate_public_merchant_cohort"
    description: str = "Aggregate public signals for an explicitly selected merchant cohort."
    args_schema: Type[BaseModel] = GatewayAggregateCohortInput

    def _run(self, **kwargs: Any) -> str:
        return self._invoke(kwargs, lambda: self.gateway.run_public_cohort_operation("aggregate", **kwargs))


class GatewayCompareOwnerCohortTool(_GatewayTool):
    name: str = "compare_owner_to_public_cohort"
    description: str = "Compare current owner public signals to a public cohort aggregate."
    args_schema: Type[BaseModel] = CompareOwnerToPublicCohortInput

    def _run(self, **kwargs: Any) -> str:
        return self._invoke(
            kwargs,
            lambda: self.gateway.run_public_cohort_operation("compare_owner", **kwargs),
        )


class GatewayPolicySearchTool(_GatewayTool):
    name: str = "search_policy_documents"
    description: str = (
        "Search official Green SM policy chunks. Use for fees, incentives, terms, "
        "procedures, privacy, and policy-aware merchant recommendations."
    )
    args_schema: Type[BaseModel] = PolicySearchInput

    def _run(self, **kwargs: Any) -> str:
        return self._invoke(kwargs, lambda: self.gateway.run_policy_search(**kwargs))


class RunScopedMerchantToolGateway:
    """Creates tools whose data access is constrained by one merchant chat run."""

    def __init__(
        self,
        *,
        context: AgenticRunContext,
        db: Session,
        cache: CachePort | None,
        emit: Any,
        db_factory: Callable[[], Session] | None = None,
        sql_event_callback: Callable[[dict[str, Any]], None] | None = None,
        trace_collector: TraceCollector | None = None,
        tool_correlation_bridge: ToolCorrelationBridge | None = None,
    ) -> None:
        self.context = context
        self._db = db
        self._db_factory = db_factory
        self._cache = cache
        self._emit_callback = emit
        self._sql_event_callback = sql_event_callback
        self._trace_collector = trace_collector
        self.tool_correlation_bridge = tool_correlation_bridge or ToolCorrelationBridge()
        self._active_tool_invocation: ContextVar[GatewayToolInvocation | None] = ContextVar(
            f"merchant_tool_invocation_{id(self)}", default=None
        )
        self._policy = MerchantDataPolicy(context.owner_merchant_id)
        self._cohort_refs: dict[str, list[str]] = {}
        self._cohort_members: dict[str, list[dict[str, Any]]] = {}
        self._latest_public_search_members: list[dict[str, Any]] = []
        self._known_public_merchant_ids: set[str] = set()

    def allow_public_merchant_ids(self, merchant_ids: list[str]) -> None:
        self._known_public_merchant_ids.update(str(value) for value in merchant_ids if value)

    def latest_public_search_members(self) -> list[dict[str, Any]]:
        """Return the public discovery evidence most recently observed this run."""
        return list(self._latest_public_search_members)

    @contextmanager
    def _tool_session(self) -> Iterator[Session]:
        """Give each tool invocation an isolated SQLAlchemy session.

        CrewAI may execute delegated tools on different workers.  A SQLAlchemy
        Session is not concurrency-safe, so the flow injects SessionLocal in
        production while unit tests can keep one mock/test transaction.
        """
        if self._db_factory is None:
            yield self._db
            return
        tool_db = self._db_factory()
        try:
            if self._sql_event_callback is None:
                yield tool_db
            else:
                with SqlQueryMonitor(self._sql_event_callback).capture(tool_db):
                    yield tool_db
        finally:
            tool_db.close()

    def _emit(self, event: str, **payload: Any) -> None:
        self._emit_callback(
            sanitize_developer_trace(
                {
                    "event": event,
                    "trace_id": self.context.trace_id,
                    **payload,
                }
            )
        )

    @contextmanager
    def trace_tool_invocation(
        self, agent_name: str, tool_name: str, raw_args: dict[str, Any]
    ) -> Iterator[None]:
        """Bind a run-local SDK correlation record to this concrete invocation."""
        invocation = self.tool_correlation_bridge.begin_gateway_call(
            agent_name, tool_name, raw_args
        )
        token = self._active_tool_invocation.set(invocation)
        try:
            yield
        finally:
            self._active_tool_invocation.reset(token)

    def tools_for(self, agent_name: str) -> list[BaseTool]:
        market_tools: list[BaseTool] = [
            GatewaySearchMerchantsTool(gateway=self, agent_name=agent_name),
        ]
        if self._known_public_merchant_ids:
            market_tools.append(
                GatewayPublicMerchantDetailTool(gateway=self, agent_name=agent_name)
            )
        tools: dict[str, list[BaseTool]] = {
            "market_search": market_tools,
            "cohort_analysis": [
                GatewaySearchMerchantsTool(gateway=self, agent_name=agent_name),
                GatewayAggregateCohortTool(gateway=self, agent_name=agent_name),
                GatewayCompareOwnerCohortTool(gateway=self, agent_name=agent_name),
                GatewayOwnerBenchmarkTool(gateway=self, agent_name=agent_name),
            ],
            "self_analysis": [
                GatewayOwnerProfileTool(gateway=self, agent_name=agent_name),
                GatewayOwnerMetricsTool(gateway=self, agent_name=agent_name),
                GatewayOwnerReviewsTool(gateway=self, agent_name=agent_name),
                GatewayOwnerComplaintsTool(gateway=self, agent_name=agent_name),
                GatewayOwnerMenuTool(gateway=self, agent_name=agent_name),
                GatewayOwnerImageComparisonTool(gateway=self, agent_name=agent_name),
                GatewayOwnerDiagnosisTool(gateway=self, agent_name=agent_name),
                GatewayOwnerRecommendationTool(gateway=self, agent_name=agent_name),
            ],
            # The verifier evaluates the dossier supplied by the coordinator;
            # it must not expand scope by fetching independent data.
            "evidence_verifier": [],
            "policy_document": [
                GatewayPolicySearchTool(gateway=self, agent_name=agent_name),
            ],
        }
        return tools.get(agent_name, [])

    def run_market_search(self, **raw_args: Any) -> str:
        args = SearchMerchantsInput.model_validate(raw_args).model_dump()
        args["city"] = normalize_city_slugs(args.get("city"))
        args, removed_fields = self._ground_search_args(args)
        if removed_fields:
            self._emit(
                "tool_args_normalized",
                tool_name="search_merchants",
                agent_name="market_search",
                removed_fields=removed_fields,
                reason="not_grounded_in_owner_request",
            )
        started = time.perf_counter()
        tool_span_id: str | None = None
        invocation = self._active_tool_invocation.get()
        if self._trace_collector:
            tool_span_id = self._trace_collector.observe_gateway_tool_started(
                "market_search",
                "search_merchants",
                args,
                correlation_id=invocation.correlation_id if invocation else None,
            )
        if invocation:
            self.tool_correlation_bridge.register_gateway_span(invocation, tool_span_id)
        self._emit(
            "tool_started",
            tool_name="search_merchants",
            agent_name="market_search",
            args=args,
            correlation_id=invocation.correlation_id if invocation else None,
        )
        try:
            with self._tool_session() as tool_db:
                result = search_merchants(
                    db=tool_db,
                    cache=self._cache,
                    cache_event_callback=lambda cache_event: self._emit(
                        "cache", **cache_event
                    ),
                    **args,
                )
            result["merchants"] = [
                self._policy.competitor_public(merchant)
                for merchant in result.get("merchants", [])
            ]
            self._latest_public_search_members = result["merchants"]
            merchant_ids = [
                str(merchant["merchant_id"])
                for merchant in result["merchants"]
                if merchant.get("merchant_id")
            ]
            if merchant_ids:
                self.allow_public_merchant_ids(merchant_ids)
                cohort_ref = f"search_{len(self._cohort_refs) + 1}"
                self._cohort_refs[cohort_ref] = merchant_ids
                self._cohort_members[cohort_ref] = result["merchants"]
                result["cohort_ref"] = cohort_ref
        except Exception as error:
            if self._trace_collector:
                self._trace_collector.observe_gateway_tool_failed(
                    "market_search",
                    "search_merchants",
                    error=error,
                    latency_ms=round((time.perf_counter() - started) * 1000, 3),
                    span_id=tool_span_id,
                )
            self._emit(
                "error",
                tool_name="search_merchants",
                agent_name="market_search",
                error_code=type(error).__name__,
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
            )
            raise
        self._emit(
            "tool_finished",
            tool_name="search_merchants",
            agent_name="market_search",
            status=result.get("status", "ok"),
            count=result.get("count", 0),
            result=result,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            correlation_id=invocation.correlation_id if invocation else None,
        )
        if self._trace_collector:
            self._trace_collector.observe_gateway_tool_finished(
                "market_search",
                "search_merchants",
                result=result,
                status=result.get("status", "ok"),
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                span_id=tool_span_id,
            )
        return json.dumps(result, ensure_ascii=False)

    def run_public_detail(self, **raw_args: Any) -> str:
        args = PublicMerchantDetailInput.model_validate(raw_args).model_dump()
        target = str(args["merchant_id"])
        if target == self.context.owner_merchant_id:
            raise ValueError(
                "Owner merchant_id is not a public-search target; use an owner tool."
            )
        if target not in self._known_public_merchant_ids:
            raise ValueError(
                "Public merchant_id was not resolved or returned by search_merchants; "
                "search for the named merchant first."
            )
        return self._execute(
            tool_name="get_public_merchant_detail",
            agent_name="market_search",
            args=args,
            execute=lambda: self._with_tool_session(
                lambda db: self._policy.competitor_public(
                    get_public_merchant_detail(
                        merchant_id=args["merchant_id"],
                        menu_limit=args["menu_limit"],
                        db=db,
                        cache=self._cache,
                        cache_event_callback=lambda event: self._emit("cache", **event),
                    )
                )
            ),
        )

    def run_policy_search(self, **raw_args: Any) -> str:
        args = PolicySearchInput.model_validate(raw_args).model_dump()
        return self._execute(
            tool_name="search_policy_documents",
            agent_name="policy_document",
            args=args,
            execute=lambda: self._with_tool_session(
                lambda db: PolicyRagService(db).search(**args)
            ),
        )

    def _ground_search_args(
        self,
        args: dict[str, Any],
    ) -> tuple[dict[str, Any], list[str]]:
        """Drop model-invented optional filters before a public search.

        This is a generic policy boundary, not intent routing: an optional
        filter is retained only when the owner actually mentioned it.  The
        free-text query remains available for semantic search.
        """
        request = normalize_text(self.context.user_query)
        normalized = dict(args)
        removed: list[str] = []
        if not request:
            # Direct gateway use in tests/maintenance jobs may not have a chat
            # utterance to ground against; do not silently alter its contract.
            return normalized, removed

        def mentioned(value: Any) -> bool:
            if value is None:
                return False
            return normalize_text(str(value)) in request

        def remove(field: str) -> None:
            if normalized.get(field) is not None:
                normalized[field] = None
                removed.append(field)

        city = normalized.get("city")
        if city:
            city_names = [slug.replace("_", " ") for slug in city.split(",")]
            if not any(name in request for name in city_names):
                remove("city")

        for field in (
            "cuisine",
            "category",
            "district",
            "ingredient",
            "diet",
            "taste",
            "customer_segment",
            "tier",
            "price_level",
        ):
            if normalized.get(field) is not None and not mentioned(normalized[field]):
                remove(field)
        if normalize_text(str(normalized.get("diet") or "")) in {"khong", "co"}:
            remove("diet")

        has_number = bool(re.search(r"\d", request))
        has_price_signal = any(
            token in request for token in ("gia", "dong", "vnd", "nghin")
        ) or bool(re.search(r"\b\d+(?:[.,]\d+)?\s*k\b", request))
        if not (has_number and has_price_signal):
            remove("min_menu_price")
            remove("max_menu_price")

        has_rating_signal = any(token in request for token in ("rating", "danh gia", "sao"))
        if not (has_number and has_rating_signal):
            remove("min_rating")

        has_nearby_signal = any(
            token in request for token in ("gan", "xung quanh", "quanh", "ban kinh")
        )
        if not has_nearby_signal:
            remove("anchor_merchant_id")
            remove("radius_km")
        else:
            # "Gần đây" is answerable from the owner location. Keep search
            # deterministic instead of requiring the model to invent a center
            # or asking the owner for an optional radius.
            normalized["anchor_merchant_id"] = self.context.owner_merchant_id
            if normalized.get("radius_km") is None or not has_number:
                normalized["radius_km"] = 5.0

        sort_by = normalized.get("sort_by")
        if sort_by == "rating" and not has_rating_signal:
            normalized["sort_by"] = "relevance"
            removed.append("sort_by")
        elif sort_by == "distance" and not has_nearby_signal:
            normalized["sort_by"] = "relevance"
            removed.append("sort_by")
        return normalized, removed

    def run_owner_image_comparison(self, **raw_args: Any) -> str:
        """Compare owner image metadata with a public cohort from this run."""
        args = OwnerImageComparisonInput.model_validate(raw_args).model_dump()
        search_ref = args.pop("search_ref", None)
        competitor_ids = args.pop("competitor_merchant_ids", None)
        if search_ref:
            competitor_ids = self._cohort_refs.get(search_ref)
            if competitor_ids is None:
                raise ValueError(f"Unknown cohort search_ref: {search_ref}")
        if not competitor_ids:
            raise ValueError(
                "competitor_merchant_ids or a run-scoped search_ref is required"
            )
        trace_args = {
            "search_ref": search_ref,
            "competitor_merchant_ids": competitor_ids,
            "limit_per_side": args["limit_per_side"],
        }
        return self._execute(
            tool_name="compare_merchant_images",
            agent_name="self_analysis",
            args=trace_args,
            execute=lambda: self._with_tool_session(
                lambda db: compare_merchant_images(
                    owner_merchant_id=self.context.owner_merchant_id,
                    competitor_merchant_ids=competitor_ids,
                    limit_per_side=args["limit_per_side"],
                    db=db,
                )
            ),
        )

    def run_owner_operation(self, operation: str, **raw_args: Any) -> str:
        """Validate, owner-bind, trace, and execute one owner-private operation."""
        registry: dict[str, tuple[str, str, Type[BaseModel], Any]] = {
            "profile": (
                "get_owner_profile_summary",
                "self_analysis",
                GetMerchantProfileSummaryInput,
                lambda args, db: get_merchant_profile_summary(
                    merchant_id=self.context.owner_merchant_id,
                    dimensions=args.get("dimensions"),
                    db=db,
                    cache=self._cache,
                ),
            ),
            "metrics": (
                "get_owner_operational_metrics",
                "self_analysis",
                GetMerchantOperationalMetricsInput,
                lambda args, db: get_merchant_operational_metrics(
                    merchant_id=self.context.owner_merchant_id,
                    db=db,
                    cache=self._cache,
                ),
            ),
            "reviews": (
                "get_owner_reviews",
                "self_analysis",
                GetMerchantReviewsInput,
                lambda args, db: get_merchant_reviews(
                    merchant_id=self.context.owner_merchant_id,
                    sentiment=args.get("sentiment"),
                    limit_samples=args.get("limit_samples", 5),
                    db=db,
                ),
            ),
            "complaints": (
                "get_owner_complaints",
                "self_analysis",
                GetMerchantComplaintsInput,
                lambda args, db: get_merchant_complaints(
                    merchant_id=self.context.owner_merchant_id,
                    category=args.get("category"),
                    severity=args.get("severity"),
                    limit_samples=args.get("limit_samples", 3),
                    db=db,
                ),
            ),
            "menu": (
                "get_owner_menu_and_food_images",
                "self_analysis",
                GetMenuAndFoodImagesInput,
                lambda args, db: get_menu_and_food_images(
                    merchant_id=self.context.owner_merchant_id,
                    only_with_images=args.get("only_with_images", False),
                    min_image_quality=args.get("min_image_quality"),
                    category=args.get("category"),
                    limit=args.get("limit", 10),
                    db=db,
                ),
            ),
            "diagnosis": (
                "diagnose_owner_merchant",
                "self_analysis",
                OwnerBoundInput,
                lambda args, db: diagnose_merchant(self.context.owner_merchant_id, db=db),
            ),
            "recommendation": (
                "recommend_owner_improvements",
                "self_analysis",
                OwnerBoundInput,
                lambda args, db: recommend_improvements(self.context.owner_merchant_id, db=db),
            ),
            "benchmark": (
                "compare_owner_to_nearby_public_merchants",
                "cohort_analysis",
                CompareMerchantBenchmarkInput,
                lambda args, db: compare_merchant_benchmark(
                    merchant_id=self.context.owner_merchant_id,
                    radius_km=args.get("radius_km", 5.0),
                    limit=args.get("limit", 5),
                    cuisine=args.get("cuisine"),
                    category=args.get("category"),
                    dimensions=args.get("dimensions"),
                    db=db,
                    cache=self._cache,
                ),
            ),
        }
        tool_name, agent_name, schema, execute = registry[operation]
        # The public tool contract intentionally omits merchant_id.  Bind it
        # before validating against the underlying data-access schema.
        args = schema.model_validate(
            {**raw_args, "merchant_id": self.context.owner_merchant_id}
        ).model_dump()
        return self._execute(
            tool_name=tool_name,
            agent_name=agent_name,
            args=args,
            execute=lambda: self._with_tool_session(
                lambda db: self._project_operation_result(operation, execute(args, db))
            ),
        )

    @staticmethod
    def _project_operation_result(operation: str, result: dict[str, Any]) -> dict[str, Any]:
        """Ensure competitor results never retain owner-private dimensions."""
        if operation != "benchmark":
            return result
        for competitor in result.get("competitors", []):
            for field in ("scores", "delta_vs_target"):
                values = competitor.get(field)
                if isinstance(values, dict):
                    competitor[field] = {
                        key: value
                        for key, value in values.items()
                        if key in PUBLIC_DIMENSIONS
                    }
        return result

    def run_public_cohort_operation(self, operation: str, **raw_args: Any) -> str:
        """Run an aggregate-only cohort operation; no competitor-private fields exist."""
        if operation == "aggregate":
            args = GatewayAggregateCohortInput.model_validate(raw_args).model_dump()
            search_ref = args.pop("search_ref", None)
            if search_ref:
                merchant_ids = self._cohort_refs.get(search_ref)
                if merchant_ids is None:
                    raise ValueError(f"Unknown cohort search_ref: {search_ref}")
                args["merchant_ids"] = merchant_ids
            if not args.get("merchant_ids"):
                raise ValueError("merchant_ids or a run-scoped search_ref is required")

            def aggregate() -> dict[str, Any]:
                result = self._with_tool_session(
                    lambda db: aggregate_public_merchant_cohort(db=db, **args)
                )
                if search_ref:
                    result = dict(result)
                    result["cohort_members"] = self._cohort_members[search_ref]
                return result

            return self._execute(
                tool_name="aggregate_public_merchant_cohort",
                agent_name="cohort_analysis",
                args=args,
                execute=aggregate,
            )
        args = CompareOwnerToPublicCohortInput.model_validate(raw_args).model_dump()
        args["owner_merchant_id"] = self.context.owner_merchant_id
        return self._execute(
            tool_name="compare_owner_to_public_cohort",
            agent_name="cohort_analysis",
            args=args,
            execute=lambda: self._with_tool_session(
                lambda db: compare_owner_to_public_cohort(db=db, **args)
            ),
        )

    def _with_tool_session(self, operation: Callable[[Session], dict[str, Any]]) -> dict[str, Any]:
        with self._tool_session() as tool_db:
            return operation(tool_db)

    def _execute(
        self,
        *,
        tool_name: str,
        agent_name: str,
        args: dict[str, Any],
        execute: Any,
    ) -> str:
        started = time.perf_counter()
        tool_span_id: str | None = None
        invocation = self._active_tool_invocation.get()
        if self._trace_collector:
            tool_span_id = self._trace_collector.observe_gateway_tool_started(
                agent_name,
                tool_name,
                args,
                correlation_id=invocation.correlation_id if invocation else None,
            )
        if invocation:
            self.tool_correlation_bridge.register_gateway_span(invocation, tool_span_id)
        self._emit(
            "tool_started",
            tool_name=tool_name,
            agent_name=agent_name,
            args=args,
            correlation_id=invocation.correlation_id if invocation else None,
        )
        try:
            result = execute()
        except Exception as error:
            if self._trace_collector:
                self._trace_collector.observe_gateway_tool_failed(
                    agent_name,
                    tool_name,
                    error=error,
                    latency_ms=round((time.perf_counter() - started) * 1000, 3),
                    span_id=tool_span_id,
                )
            self._emit(
                "error",
                tool_name=tool_name,
                agent_name=agent_name,
                error_code=type(error).__name__,
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
            )
            raise
        self._emit(
            "tool_finished",
            tool_name=tool_name,
            agent_name=agent_name,
            status=result.get("status", "ok"),
            result=result,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            correlation_id=invocation.correlation_id if invocation else None,
        )
        if self._trace_collector:
            self._trace_collector.observe_gateway_tool_finished(
                agent_name,
                tool_name,
                result=result,
                status=result.get("status", "ok"),
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
                span_id=tool_span_id,
            )
        return json.dumps(result, ensure_ascii=False)
