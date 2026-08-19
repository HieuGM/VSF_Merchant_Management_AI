"""Terminal specialist execution and parallel dispatch."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from crewai import Agent, Crew, Process, Task
from langfuse import get_client
from sqlalchemy.orm import Session

from models.merchant_execution import CapabilityName, PlannedTask
from services.merchant_prompts import get_merchant_prompt
from tools.merchant.gateway import RunScopedMerchantToolGateway

CAPABILITY_PROMPT_KEYS: dict[CapabilityName, str] = {
    "owner": "owner",
    "market": "market",
    "policy": "policy",
    "review": "review",
    "cohort": "cohort",
}

CAPABILITY_ROLES: dict[CapabilityName, tuple[str, str]] = {
    "owner": (
        "Owner Performance Analysis Specialist",
        "Analyze merchant owner operational data, profile, menu, ratings, and metrics.",
    ),
    "market": (
        "Public Market Search Specialist",
        "Search and analyze public merchant market data and listings.",
    ),
    "policy": (
        "Green SM Policy Document Specialist",
        "Search and explain Green SM merchant policies and guidelines.",
    ),
    "review": (
        "Customer Review Specialist",
        "Analyze customer reviews, complaints, and satisfaction feedback.",
    ),
    "cohort": (
        "Public Cohort Analysis Specialist",
        "Analyze benchmark metrics across merchant cohorts.",
    ),
}

GatewayFactory = Callable[[], tuple[RunScopedMerchantToolGateway, Session | None]]


@dataclass(frozen=True)
class SpecialistResult:
    """Standard outcome from one specialist execution."""

    capability: CapabilityName
    instruction: str
    status: Literal["completed", "failed"]
    content: str
    duration_ms: float = 0.0
    error: str | None = None
    public_merchants: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: int = 0


def build_specialist(
    capability: CapabilityName,
    *,
    gateway: RunScopedMerchantToolGateway,
    llm: Any,
    label: str | None = None,
) -> Agent:
    """Build a terminal CrewAI specialist agent bounded by capability tools."""
    prompt_key = CAPABILITY_PROMPT_KEYS[capability]
    prompt_obj = get_merchant_prompt(prompt_key, label=label)

    default_role, default_goal = CAPABILITY_ROLES.get(
        capability, (f"{capability} Specialist", f"Execute {capability} tasks")
    )
    goal = prompt_obj.prompt.strip() if hasattr(prompt_obj, "prompt") else default_goal
    tools = gateway.tools_for(capability)

    return Agent(
        role=default_role,
        goal=goal,
        backstory="You work only from the conversation context and gateway tool observations. You must never assume unverified facts. You cannot delegate.",
        tools=tools,
        llm=llm,
        allow_delegation=False,
        max_iter=4,
        verbose=False,
    )


def execute_specialist(
    task: PlannedTask,
    *,
    gateway: RunScopedMerchantToolGateway,
    llm: Any,
    trace_context: dict[str, str] | None = None,
    label: str | None = None,
) -> SpecialistResult:
    """Execute a single specialist task and return bounded SpecialistResult."""
    client = get_client()
    start_time = time.monotonic()

    with client.start_as_current_observation(
        trace_context=trace_context,
        name=f"specialist.{task.capability}",
        as_type="agent",
        input=task.instruction,
        metadata={"capability": task.capability},
    ) as observation:
        agent = build_specialist(task.capability, gateway=gateway, llm=llm, label=label)
        crew_task = Task(
            description=task.instruction,
            expected_output="A bounded, self-contained user-facing answer based only on tool evidence.",
            agent=agent,
        )
        crew = Crew(
            agents=[agent],
            tasks=[crew_task],
            process=Process.sequential,
            memory=False,
            verbose=False,
        )

        try:
            output = crew.kickoff()
            content = output.raw if hasattr(output, "raw") else str(output)
            tool_calls = gateway.completed_tool_calls

            # Failure rule: zero observed tool calls -> no_tool_evidence
            if tool_calls == 0 and not content:
                status = "failed"
                error = "no_tool_evidence"
            else:
                status = "completed"
                error = None

            duration_ms = (time.monotonic() - start_time) * 1000
            res = SpecialistResult(
                capability=task.capability,
                instruction=task.instruction,
                status=status,
                content=content,
                duration_ms=duration_ms,
                error=error,
                public_merchants=gateway.collected_public_merchants,
                tool_calls=tool_calls,
            )
            observation.update(
                output=res.content,
                level="ERROR" if res.status == "failed" else "DEFAULT",
            )
            return res
        except Exception as exc:
            duration_ms = (time.monotonic() - start_time) * 1000
            res = SpecialistResult(
                capability=task.capability,
                instruction=task.instruction,
                status="failed",
                content="",
                duration_ms=duration_ms,
                error=str(exc),
                public_merchants=gateway.collected_public_merchants,
                tool_calls=gateway.completed_tool_calls,
            )
            observation.update(
                output=f"Specialist {task.capability} failed: {exc}",
                level="ERROR",
            )
            return res


def execute_parallel(
    tasks: list[PlannedTask],
    *,
    gateway_factory: GatewayFactory,
    llm: Any,
    trace_context: dict[str, str] | None = None,
    label: str | None = None,
) -> list[SpecialistResult]:
    """Execute multiple specialist tasks concurrently and preserve task order."""
    if not tasks:
        return []

    if len(tasks) == 1:
        gw, db = gateway_factory()
        try:
            return [execute_specialist(tasks[0], gateway=gw, llm=llm, trace_context=trace_context, label=label)]
        finally:
            if db is not None:
                db.close()

    results_by_index: dict[int, SpecialistResult] = {}
    workers = min(4, len(tasks))

    def _run_branch(idx: int, t: PlannedTask) -> tuple[int, SpecialistResult]:
        branch_gw, branch_db = gateway_factory()
        try:
            res = execute_specialist(t, gateway=branch_gw, llm=llm, trace_context=trace_context, label=label)
            return idx, res
        finally:
            if branch_db is not None:
                branch_db.close()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_run_branch, i, task) for i, task in enumerate(tasks)]
        for fut in as_completed(futures):
            idx, result = fut.result()
            results_by_index[idx] = result

    return [results_by_index[i] for i in range(len(tasks))]
