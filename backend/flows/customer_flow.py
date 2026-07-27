"""Customer flow (G-02) — CrewAI Crew orchestration + run/event persistence.

Phase 06: replaces the Phase-0b direct tool call with a real `CustomerDiscoveryCrew`
kickoff. The flow owns the run lifecycle (agent_runs + run_started/run_finished events);
the PersistingListener persists tool/task trace events emitted by CrewAI during kickoff.
Every run carries a `trace_id` (§11.4) so events and results correlate.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agents.listeners.crewai_listener import build_event_record
from agents.listeners.persisting_listener import install_persisting_listener, run_scope
from agents.tool_adapter import tool_call_scope
from core.tracing import new_id
from models.agent import AgentRunRecord, CustomerChatResponse
from repositories.agent_run_repository import AgentRunRepository
from tools.registry import registry

_CREW_NAME = "customer_discovery"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CustomerFlow:
    """Customer discovery flow — runs the CrewAI crew and persists observability."""

    def __init__(self) -> None:
        # Discover the customer + shared tools once so the registry/adapter can bind them.
        # Guarded so constructing multiple flows never double-registers (registry is a
        # process singleton and raises on duplicate names).
        existing = set(registry.names())
        if "get_merchant_profile" not in existing:
            registry.auto_discover("tools.shared")
        if "merchant_search" not in existing:
            registry.auto_discover("tools.customer")
        install_persisting_listener()
        self._repo = AgentRunRepository()

    def search_restaurants(
        self,
        *,
        query: str | None = None,
        cuisine: str | None = None,
        city: str | None = None,
        budget: str | None = None,
        lat: float | None = None,
        lng: float | None = None,
        radius_km: float | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        crew: Any = None,
    ) -> CustomerChatResponse:
        """Run the Customer Discovery Crew for a discovery query (UC-04/UC-05).

        `crew` may be injected (tests pass a mock/crew with fake LLMs); otherwise the
        live NVIDIA NIM crew is built. Returns a `CustomerChatResponse`."""
        trace_id = new_id("trace")

        self._repo.create_run(
            AgentRunRecord(
                trace_id=trace_id,
                session_id=session_id,
                user_id=user_id,
                crew_name=_CREW_NAME,
                intent="restaurant_discovery",
                status="running",
                started_at=_utc_now_iso(),
            )
        )
        self._repo.add_event(
            build_event_record(
                trace_id=trace_id,
                event_type="run_started",
                agent_name="customer_flow",
                task_name="search_restaurants",
                input_payload={
                    "query": query,
                    "cuisine": cuisine,
                    "city": city,
                    "budget": budget,
                    "location": {"lat": lat, "lng": lng} if lat is not None else None,
                },
            )
        )

        # Geo: when the user supplied coords, default radius to 5km so the search_task
        # prompt has a concrete radius (and the search agent is locked to nearby_merchant_search
        # — see build_customer_crew(has_location=...)). Without this, radius_km="" leaks through
        # and the agent can return country-wide results.
        has_location = lat is not None and lng is not None
        if has_location and radius_km is None:
            radius_km = 5.0

        inputs = _build_inputs(
            query=query, cuisine=cuisine, city=city, budget=budget,
            lat=lat, lng=lng, radius_km=radius_km,
            user_id=user_id, session_id=session_id,
        )

        try:
            if crew is None:
                from agents.customer.customer_crew import build_customer_crew

                crew = build_customer_crew(has_location=has_location)

            with run_scope(trace_id, self._repo), tool_call_scope():
                crew_output = crew.kickoff(inputs=inputs)

            response = _to_chat_response(trace_id, session_id, crew_output)

            self._repo.add_event(
                build_event_record(
                    trace_id=trace_id,
                    event_type="run_finished",
                    agent_name="customer_flow",
                    task_name="search_restaurants",
                    output_summary={"result_count": len(response.results)},
                )
            )
            self._repo.finish_run(trace_id, status="ok", finished_at=_utc_now_iso())
            return response

        except Exception as exc:  # noqa: BLE001 - persist error, never crash the process
            self._repo.add_event(
                build_event_record(
                    trace_id=trace_id,
                    event_type="error",
                    agent_name="customer_flow",
                    task_name="search_restaurants",
                    status="error",
                    error_code=type(exc).__name__,
                    output_summary={"error": str(exc)},
                )
            )
            self._repo.finish_run(
                trace_id,
                status="error",
                error_code=type(exc).__name__,
                finished_at=_utc_now_iso(),
            )
            raise


def _build_inputs(
    *,
    query: str | None,
    cuisine: str | None,
    city: str | None,
    budget: str | None,
    lat: float | None,
    lng: float | None,
    radius_km: float | None,
    user_id: str | None,
    session_id: str | None,
) -> dict[str, Any]:
    """Fill every `{var}` referenced by the task YAML; None → "" to avoid literal braces."""
    return {
        "query": query or "",
        "cuisine": cuisine or "",
        "city": city or "",
        "budget": budget or "",
        "lat": lat if lat is not None else "",
        "lng": lng if lng is not None else "",
        "radius_km": radius_km if radius_km is not None else "",
        "user_id": user_id or "",
        "session_id": session_id or "",
    }


def _task_pydantic(crew_output: Any, model_name: str) -> Any | None:
    """Find a task output whose pydantic model matches `model_name` (defensive)."""
    for task_out in getattr(crew_output, "tasks_output", []) or []:
        pyd = getattr(task_out, "pydantic", None)
        if pyd is not None and type(pyd).__name__ == model_name:
            return pyd
    return None


def _to_chat_response(trace_id: str, session_id: str | None, crew_output: Any) -> CustomerChatResponse:
    """Map a CrewAI CrewOutput to the CustomerChatResponse contract (§11.4).

    Reads structured task outputs when present; falls back to the raw string for the
    answer. Never assumes LLM content — only shape."""
    search = _task_pydantic(crew_output, "SearchTaskOutput")
    preference = _task_pydantic(crew_output, "PreferenceTaskOutput")
    explanation = _task_pydantic(crew_output, "ExplanationTaskOutput")

    results = (
        [c.model_dump() for c in search.candidates] if search is not None else []
    )
    suggestions = (
        [s.model_dump() for s in preference.suggestions] if preference is not None else []
    )
    if explanation is not None:
        answer = explanation.answer
    else:
        answer = str(getattr(crew_output, "raw", "") or crew_output or "")

    return CustomerChatResponse(
        trace_id=trace_id,
        session_id=session_id,
        intent="restaurant_discovery",
        answer=answer,
        results=results,
        preference_suggestions=suggestions,
    )


# Singleton instance (kept for existing import sites).
customer_flow = CustomerFlow()
