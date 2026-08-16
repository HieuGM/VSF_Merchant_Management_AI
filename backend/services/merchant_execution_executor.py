"""Direct and parallel execution of coordinator-planned specialist tasks."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from crewai import Agent, Crew, Process, Task

from models.merchant_execution import CapabilityName, PlannedTask
from tools.merchant.gateway import RunScopedMerchantToolGateway


from services.merchant_prompts import get_merchant_prompt

CAPABILITY_PROMPT_KEYS: dict[CapabilityName, str] = {
    "owner": "SELF_ANALYSIS_PROMPT",
    "market": "MARKET_SEARCH_PROMPT",
    "policy": "POLICY_RAG_PROMPT",
    "review": "SELF_ANALYSIS_PROMPT",
    "cohort": "COHORT_ANALYSIS_PROMPT",
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


@dataclass(frozen=True)
class SpecialistResult:
    """Standard outcome from one specialist execution."""

    capability: CapabilityName
    instruction: str
    status: Literal["completed", "failed"]
    content: str
    duration_ms: float
    error: str | None = None
    public_merchants: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: int = 0


def _build_specialist_agent(
    capability: CapabilityName,
    *,
    gateway: RunScopedMerchantToolGateway,
    llm: Any,
) -> Agent:
    prompt_key = CAPABILITY_PROMPT_KEYS.get(capability)
    goal = None
    if prompt_key:
        try:
            prompt_obj = get_merchant_prompt(prompt_key)
            goal = prompt_obj.prompt.strip()
        except Exception:
            pass

    default_role, default_goal = CAPABILITY_ROLES.get(
        capability, (f"{capability} Specialist", f"Execute {capability} tasks")
    )
    role = default_role
    if not goal:
        goal = default_goal

    tools = gateway.tools_for(capability)
    return Agent(
        role=role,
        goal=goal,
        backstory="You work only from the conversation context and gateway tool observations. You must never assume unverified facts.",
        tools=tools,
        llm=llm,
        allow_delegation=False,
        max_iter=2,
        max_execution_time=120,
        verbose=False,
    )


def execute_direct(
    task: PlannedTask,
    *,
    gateway: RunScopedMerchantToolGateway,
    llm: Any,
    response_type: Literal["fact", "summary", "analysis"] = "summary",
) -> SpecialistResult:
    """Execute a single specialist task directly without manager delegation."""
    started_at = time.perf_counter()
    try:
        specialist = _build_specialist_agent(task.capability, gateway=gateway, llm=llm)
        expected_outputs = {
            "fact": "A concise, single-part factual answer based strictly on retrieved tool evidence.",
            "summary": "A clear, structured summary based strictly on retrieved tool evidence.",
            "analysis": "A detailed, grounded analysis backed by evidence from tools.",
        }
        expected_output = expected_outputs.get(response_type, "A grounded answer based strictly on tool evidence.")

        evidence_contract = (
            f"{task.instruction}\n\n"
            "STRICT GROUNDING CONTRACT:\n"
            "1. You MUST use available tools to retrieve necessary data.\n"
            "2. Rely ONLY on data returned by tool observations.\n"
            "3. Do NOT invent, assume, or output unverified numbers or merchant details."
        )

        output_text = _kickoff_specialist(specialist, evidence_contract, expected_output)
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        tool_calls = _completed_tool_calls(gateway)
        public_merchants = (
            gateway.latest_public_search_members()
            if hasattr(gateway, "latest_public_search_members")
            else []
        )

        # Output validation check: non-empty grounded output required
        if not output_text:
            return SpecialistResult(
                capability=task.capability,
                instruction=task.instruction,
                status="failed",
                content="Specialist execution returned empty content.",
                duration_ms=duration_ms,
                error="empty_output",
                public_merchants=public_merchants,
                tool_calls=tool_calls,
            )

        if tool_calls == 0:
            return SpecialistResult(
                capability=task.capability,
                instruction=task.instruction,
                status="failed",
                content="Specialist execution returned no tool evidence.",
                duration_ms=duration_ms,
                error="no_tool_evidence",
                public_merchants=public_merchants,
            )

        return SpecialistResult(
            capability=task.capability,
            instruction=task.instruction,
            status="completed",
            content=output_text,
            duration_ms=duration_ms,
            public_merchants=public_merchants,
            tool_calls=tool_calls,
        )
    except Exception as error:
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        return SpecialistResult(
            capability=task.capability,
            instruction=task.instruction,
            status="failed",
            content=f"Subsystem error executing capability '{task.capability}'.",
            duration_ms=duration_ms,
            error=str(error),
        )


def _kickoff_specialist(specialist: Agent, description: str, expected_output: str) -> str:
    task = Task(description=description, expected_output=expected_output, agent=specialist)
    result = Crew(
        agents=[specialist],
        tasks=[task],
        process=Process.sequential,
        verbose=False,
    ).kickoff()
    return str(result.raw if hasattr(result, "raw") else result).strip()


def _completed_tool_calls(gateway: Any) -> int:
    counter = getattr(gateway, "completed_tool_calls", None)
    if callable(counter):
        return int(counter())
    return int(getattr(gateway, "tool_calls", 0))


def _execute_parallel_branch(
    task: PlannedTask,
    gateway_factory: Callable[[], tuple[RunScopedMerchantToolGateway, Any | None]],
    llm: Any,
    response_type: Literal["fact", "summary", "analysis"] = "summary",
) -> SpecialistResult:
    gateway, session = gateway_factory()
    try:
        return execute_direct(task, gateway=gateway, llm=llm, response_type=response_type)
    finally:
        if session is not None and hasattr(session, "close"):
            try:
                session.close()
            except Exception:
                pass


def execute_parallel(
    tasks: list[PlannedTask],
    *,
    gateway_factory: Callable[[], tuple[RunScopedMerchantToolGateway, Any | None]],
    llm: Any,
    response_type: Literal["fact", "summary", "analysis"] = "summary",
) -> list[SpecialistResult]:
    """Execute independent specialist tasks concurrently in isolated environments."""
    if not tasks:
        return []

    max_workers = min(4, len(tasks))
    futures_map = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for idx, task in enumerate(tasks):
            future = executor.submit(
                _execute_parallel_branch,
                task,
                gateway_factory,
                llm,
                response_type,
            )
            futures_map[future] = idx

    results: list[SpecialistResult | None] = [None] * len(tasks)
    for future in as_completed(futures_map):
        idx = futures_map[future]
        task = tasks[idx]
        try:
            results[idx] = future.result()
        except Exception as error:
            results[idx] = SpecialistResult(
                capability=task.capability,
                instruction=task.instruction,
                status="failed",
                content=f"Subsystem error executing parallel capability '{task.capability}'.",
                duration_ms=0.0,
                error=str(error),
            )

    return [r for r in results if r is not None]


def merge_parallel_results(results: list[SpecialistResult]) -> str:
    """Merge specialist outputs deterministically into a single summary response."""
    parts = []
    for res in results:
        cap_title = res.capability.upper()
        if res.status == "completed":
            parts.append(f"### {cap_title}\n{res.content}")
        else:
            parts.append(f"### {cap_title}\n*(Thông tin chưa khả dụng cho tính năng này)*")
    return "\n\n".join(parts)
