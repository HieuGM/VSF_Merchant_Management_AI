"""The single production boundary that turns an input route into work.

Routing is intentionally separate from execution: callers can inspect a
``RoutingDecision`` before any CrewAI kickoff or business tool call happens.
This small seam also gives deterministic tests a truthful place to count work
without reproducing route-to-work rules in a test harness.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from services.merchant_input_router import RoutingDecision


@dataclass(frozen=True)
class RouteExecution:
    """Observable result of the work allowed by one routing decision."""

    outcome: str
    crew_result: Any | None = None


def execute_routing_decision(
    decision: RoutingDecision,
    *,
    kickoff_coordinator: Callable[[], Any] | None = None,
) -> RouteExecution:
    """Run exactly the work explicitly authorised by a deterministic route.

    ``reject`` and ``fast_answer`` are deliberately no-work outcomes.
    ``coordinate`` alone can start the injected coordinator kickoff.
    """
    if decision.outcome == "coordinate":
        if kickoff_coordinator is None:
            raise ValueError("coordinate route requires a coordinator kickoff")
        return RouteExecution(
            outcome=decision.outcome,
            crew_result=kickoff_coordinator(),
        )

    return RouteExecution(outcome=decision.outcome)
