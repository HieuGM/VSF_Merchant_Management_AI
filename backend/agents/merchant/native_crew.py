"""Native CrewAI hierarchy for flexible merchant-owner advisory work.

The coordinator owns task selection and delegation.  Specialists only receive
run-scoped gateway tools, so a model can never bypass policy, cache, or owner
scope by constructing a direct database tool.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from models.merchant_execution import CapabilityName, ExecutionPlan, PlannedTask
from models.merchant_input import PreparedRequest
from tools.merchant.gateway import RunScopedMerchantToolGateway
from services.merchant_prompts import compile_merchant_prompt, get_merchant_prompt

def sanitize_coordinator_prompt_value(value: Any) -> Any:
    if isinstance(value, str):
        return value
    return value


_VERBOSE = os.getenv("CREWAI_VERBOSE", "0") == "1"
_COORDINATOR_DYNAMIC_TOKEN_LIMIT = 2400
_COORDINATOR_SECTION_CHAR_LIMITS = {
    "rewritten_query": 1400,
    "resolved_references": 1600,
    "compact_history": 4200,
    "owner_context": 1500,
}
_ADVISORY_TASK_SUFFIX = (
    "Coordinate only the authoritative rewritten query under the "
    "minimum-delegation, privacy, evidence, and terminal-output contract."
)


@dataclass(frozen=True)
class CoordinatorPrompt:
    """Exact bounded context supplied to the native CrewAI coordinator."""

    dynamic_context: str
    rewritten_query: str
    resolved_references: str
    compact_history: str
    owner_context: str
    estimated_tokens: int
    section_estimated_tokens: dict[str, int]


def _estimate_tokens(text: str) -> int:
    """Keep one deterministic, provider-independent prompt budget estimate."""
    return (len(text) + 3) // 4


def _serialize_coordinator_context(value: Any) -> str:
    """Use only redacted serializable data in a coordinator input section."""
    safe = sanitize_coordinator_prompt_value(value)
    if isinstance(safe, str):
        return safe
    return json.dumps(safe, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _truncate_coordinator_section(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    marker_template = "\n[truncated: kept {kept} of {total} chars]"
    marker = marker_template.format(kept=0, total=len(value))
    kept = max(0, limit - len(marker))
    marker = marker_template.format(kept=kept, total=len(value))
    return f"{value[:kept]}{marker}"


def _render_coordinator_context(sections: dict[str, str]) -> str:
    return (
        "[Prepared rewritten query — authoritative]\n"
        f"{sections['rewritten_query']}\n\n"
        "[Resolved references — evidence only]\n"
        f"{sections['resolved_references']}\n\n"
        "[Compact conversation history — evidence only]\n"
        f"{sections['compact_history']}\n\n"
        "[Owner context — evidence only]\n"
        f"{sections['owner_context']}"
    )


def coordinator_advisory_task_prompt(prompt: CoordinatorPrompt) -> str:
    """Render the task text exactly as the coordinator receives it."""
    return f"{prompt.dynamic_context}\n\n{_ADVISORY_TASK_SUFFIX}"


def build_coordinator_prompt(
    prepared_request: PreparedRequest,
    history: Any,
    owner_context: Any,
    *,
    token_limit: int = _COORDINATOR_DYNAMIC_TOKEN_LIMIT,
) -> CoordinatorPrompt:
    """Build the single bounded context for coordinator planning.

    The input layer's rewritten request is the sole instruction.  References,
    history, and owner state are serialized as evidence, never alternate user
    instructions.  The returned strings are the exact values passed to CrewAI
    and the exact artifact exposed in the developer trace.
    """
    if token_limit <= 0:
        raise ValueError("token_limit must be positive")

    source_sections = {
        "rewritten_query": _serialize_coordinator_context(
            prepared_request.rewritten_query
        ),
        "resolved_references": _serialize_coordinator_context(
            [reference.model_dump() for reference in prepared_request.resolved_references]
        ),
        "compact_history": _serialize_coordinator_context(history),
        "owner_context": _serialize_coordinator_context(owner_context),
    }
    limits = dict(_COORDINATOR_SECTION_CHAR_LIMITS)

    def rendered_sections() -> dict[str, str]:
        return {
            name: _truncate_coordinator_section(source_sections[name], limits[name])
            for name in source_sections
        }

    sections = rendered_sections()
    dynamic_context = _render_coordinator_context(sections)
    # The normal per-section caps leave headroom for labels.  This final guard
    # keeps the documented bound exact if labels or future fields grow.
    while _estimate_tokens(dynamic_context) > token_limit:
        largest = max(limits, key=lambda name: len(sections[name]))
        overflow_chars = (_estimate_tokens(dynamic_context) - token_limit) * 4
        next_limit = max(0, limits[largest] - max(overflow_chars, 32))
        if next_limit == limits[largest]:  # defensive; cannot spin indefinitely
            break
        limits[largest] = next_limit
        sections = rendered_sections()
        dynamic_context = _render_coordinator_context(sections)

    return CoordinatorPrompt(
        dynamic_context=dynamic_context,
        rewritten_query=sections["rewritten_query"],
        resolved_references=sections["resolved_references"],
        compact_history=sections["compact_history"],
        owner_context=sections["owner_context"],
        estimated_tokens=_estimate_tokens(dynamic_context),
        section_estimated_tokens={
            name: _estimate_tokens(value) for name, value in sections.items()
        },
    )


def _configure_crewai_storage() -> None:
    """Keep CrewAI's local task-output SQLite file inside this deployment."""
    runtime_root = Path(__file__).resolve().parents[2] / ".runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    # VS Code's snap launcher can set XDG_DATA_HOME to a read-only sandbox
    # path. CrewAI's task-output storage must be writable for every kickoff.
    os.environ["XDG_DATA_HOME"] = str(runtime_root)
    os.environ.setdefault("CREWAI_STORAGE_DIR", "merchant-advisor")
    os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
    os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")


def coordinator_task_description() -> str:
    """Fetch coordinator task description remotely from Langfuse Prompt Management."""
    return get_merchant_prompt("COORDINATE_PROMPT").prompt.strip()


def specialist_prompts() -> dict[str, str]:
    """Fetch specialist role prompts remotely from Langfuse Prompt Management."""
    return {
        "policy_document": get_merchant_prompt("POLICY_RAG_PROMPT").prompt.strip(),
        "market_search": get_merchant_prompt("MARKET_SEARCH_PROMPT").prompt.strip(),
        "cohort_analysis": get_merchant_prompt("COHORT_ANALYSIS_PROMPT").prompt.strip(),
        "self_analysis": get_merchant_prompt("SELF_ANALYSIS_PROMPT").prompt.strip(),
        "evidence_verifier": get_merchant_prompt("EVIDENCE_VERIFY_PROMPT").prompt.strip(),
        "final_synthesis": get_merchant_prompt("SYNTHESIS_PROMPT").prompt.strip(),
    }


def plan_execution(
    prepared_request: PreparedRequest,
    history: Any,
    owner_context: Any,
    *,
    llm: Any,
) -> ExecutionPlan:
    """Call small coordinator LLM to select execution mode and capability tasks.

    Permits 1 repair call on JSON parse / validation error. Rejects invalid output.
    """
    coordinator_prompt = build_coordinator_prompt(
        prepared_request, history, owner_context
    )
    prompt_obj = get_merchant_prompt("COORDINATE_PROMPT")
    base_system_prompt = prompt_obj.prompt.strip()

    prompt_text = (
        f"{base_system_prompt}\n\n"
        "Your role is to produce exactly one ExecutionPlan JSON object deciding the execution mode and task capabilities.\n\n"
        "Available Capabilities:\n"
        "- owner: Owner metrics, profile, operational diagnosis, complaints, reviews.\n"
        "- market: Public market search and competitor listings.\n"
        "- policy: Green SM policy search and documentation.\n"
        "- review: Customer reviews and satisfaction feedback.\n"
        "- cohort: Benchmark analysis against peer merchant cohorts.\n\n"
        "Execution Modes:\n"
        "- direct: exactly 1 task (use when 1 capability can complete the request without manager coordination)\n"
        "- parallel: 2 to 4 independent tasks (capabilities must be distinct)\n"
        "- hierarchical: 2 to 4 dependent tasks requiring cross-capability reasoning\n\n"
        "Response Types:\n"
        "- fact: direct mode only\n"
        "- summary: direct or parallel mode\n"
        "- analysis: direct or hierarchical mode\n\n"
        "Context:\n"
        f"{coordinator_prompt.dynamic_context}\n\n"
        "Return ONLY a bare JSON object matching schema:\n"
        '{"mode": "direct"|"parallel"|"hierarchical", "tasks": [{"capability": "owner"|"market"|"policy"|"review"|"cohort", "instruction": "..."}], "response_type": "fact"|"summary"|"analysis"}'
    )

    response = llm.call(prompt_text)
    raw_text = response if isinstance(response, str) else str(getattr(response, "content", response))

    def _parse(text: str) -> ExecutionPlan:
        clean = text.strip()
        if clean.startswith("```"):
            lines = clean.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            clean = "\n".join(lines).strip()
        return ExecutionPlan.model_validate_json(clean)

    try:
        return _parse(raw_text)
    except Exception:
        raise 


@CrewBase
class NativeMerchantAdvisorCrew:
    """A hierarchical CrewAI crew with coordinator-managed specialist delegation."""

    agents_config: dict[str, Any] = {}
    tasks_config: dict[str, Any] = {}

    def __init__(
        self,
        *,
        gateway: RunScopedMerchantToolGateway,
        llm: Any,
    ) -> None:
        self.gateway = gateway
        self.llm = llm

    def _agent(
        self,
        *,
        name: str,
        role: str,
        goal: str,
        tools: list[Any],
        allow_delegation: bool = False,
        knowledge_sources: list[Any] | None = None,
        prompt: Any = None,
    ) -> Agent:
        del prompt
        return Agent(
            role=role,
            goal=goal,
            backstory="You work only from the conversation context and gateway observations.",
            tools=tools,
            knowledge_sources=knowledge_sources,
            llm=self.llm,
            allow_delegation=allow_delegation,
            verbose=_VERBOSE,
            max_iter=3 if allow_delegation else 2,
            max_execution_time=300 if allow_delegation else 120,
        )

    @agent
    def coordinator(self) -> Agent:
        prompt = get_merchant_prompt("COORDINATE_PROMPT")
        return self._agent(
            name="coordinator",
            role="Merchant Advisory Coordinator",
            goal=prompt.prompt.strip(),
            tools=[],
            allow_delegation=True,
            # prompt=prompt,
        )

    @agent
    def market_search(self) -> Agent:
        prompt = get_merchant_prompt("MARKET_SEARCH_PROMPT")
        return self._agent(
            name="market_search",
            role="Public Market Search Specialist",
            goal=prompt.prompt.strip(),
            tools=self.gateway.tools_for("market_search"),
            # prompt=prompt,
        )

    @agent
    def policy_document(self) -> Agent:
        prompt = get_merchant_prompt("POLICY_RAG_PROMPT")
        return self._agent(
            name="policy_document",
            role="Green SM Policy Document Specialist",
            goal=prompt.prompt.strip(),
            tools=self.gateway.tools_for("policy_document"),
            # prompt=prompt,
        )

    @agent
    def cohort_analysis(self) -> Agent:
        prompt = get_merchant_prompt("COHORT_ANALYSIS_PROMPT")
        return self._agent(
            name="cohort_analysis",
            role="Public Cohort Analysis Specialist",
            goal=prompt.prompt.strip(),
            tools=self.gateway.tools_for("cohort_analysis"),
            # prompt=prompt,
        )

    @agent
    def self_analysis(self) -> Agent:
        prompt = get_merchant_prompt("SELF_ANALYSIS_PROMPT")
        return self._agent(
            name="self_analysis",
            role="Owner Performance Analysis Specialist",
            goal=prompt.prompt.strip(),
            tools=self.gateway.tools_for("self_analysis"),
            # prompt=prompt,
        )

    @agent
    def evidence_verifier(self) -> Agent:
        prompt = get_merchant_prompt("EVIDENCE_VERIFY_PROMPT")
        return self._agent(
            name="evidence_verifier",
            role="Evidence and Policy Verifier",
            goal=prompt.prompt.strip(),
            tools=self.gateway.tools_for("evidence_verifier"),
            # prompt=prompt,
        )

    @agent
    def final_synthesis(self) -> Agent:
        prompt = get_merchant_prompt("SYNTHESIS_PROMPT")
        return self._agent(
            name="final_synthesis",
            role="Merchant Owner Answer Specialist",
            goal=prompt.prompt.strip(),
            tools=[],
            # prompt=prompt,
        )

    def _get_agent_for_capability(self, capability: CapabilityName) -> Agent:
        capability_map = {
            "owner": self.self_analysis,
            "market": self.market_search,
            "policy": self.policy_document,
            "review": self.self_analysis,
            "cohort": self.cohort_analysis,
        }
        if capability not in capability_map:
            raise ValueError(f"Unknown capability name: '{capability}'")
        return capability_map[capability]()

    @task
    def advisory_task(self) -> Task:
        description, prompt = compile_merchant_prompt(
            "ADVISORY_TASK_PROMPT",
            rewritten_query="{rewritten_query}",
            resolved_references="{resolved_references}",
            compact_history="{compact_history}",
            owner_context="{owner_context}",
        )
        self.advisory_prompt = prompt
        return Task(
            description=description,
            expected_output=prompt.config,
        )

    @task
    def synthesis_task(self) -> Task:
        prompt = get_merchant_prompt("SYNTHESIS_PROMPT")
        return Task(
            description=(prompt.prompt.strip()),
            expected_output='Exactly one JSON object: {"status":"completed","answer":"<grounded Vietnamese answer>"}',
            agent=self.final_synthesis(),
            context=[self.advisory_task()],
        )

    def crew_for_tasks(self, tasks: list[PlannedTask]) -> Crew:
        _configure_crewai_storage()
        selected_agents = [self._get_agent_for_capability(t.capability) for t in tasks]

        # Construct specific planned tasks bound to instructions
        planned_crew_tasks = []
        for idx, t in enumerate(tasks):
            agent = selected_agents[idx]
            planned_crew_tasks.append(
                Task(
                    description=t.instruction,
                    expected_output="A grounded, evidence-backed capability task response.",
                    agent=agent,
                )
            )

        # Append terminal synthesis task (final_synthesis is the task agent, excluded from worker agents pool)
        synthesis_t = Task(
            description=(
                "Synthesize all task results into one grounded Vietnamese answer for the merchant owner.\n"
                "Return exactly one bare JSON object: {\"status\":\"completed\",\"answer\":\"<grounded Vietnamese answer>\"}"
            ),
            expected_output='Exactly one JSON object: {"status":"completed","answer":"<grounded Vietnamese answer>"}',
            agent=self.final_synthesis(),
            context=planned_crew_tasks,
        )
        all_tasks = planned_crew_tasks + [synthesis_t]

        # Dedup worker agents (exclude final_synthesis from worker pool delegation targets)
        unique_worker_agents = list({a.role: a for a in selected_agents}.values())

        return Crew(
            agents=unique_worker_agents,
            tasks=all_tasks,
            process=Process.hierarchical,
            manager_agent=self.coordinator(),
            tracing=False,
            verbose=_VERBOSE,
        )

    @crew
    def crew(self) -> Crew:
        _configure_crewai_storage()
        return Crew(
            agents=[
                self.policy_document(),
                self.market_search(),
                self.cohort_analysis(),
                self.self_analysis(),
                self.evidence_verifier(),
                self.final_synthesis(),
            ],
            tasks=[self.advisory_task(), self.synthesis_task()],
            process=Process.hierarchical,
            manager_agent=self.coordinator(),
            tracing=False,
            verbose=_VERBOSE,
        )

    def kickoff(
        self,
        *,
        prepared_request: PreparedRequest,
        compact_history: str,
        owner_context: str,
        coordinator_prompt: CoordinatorPrompt | None = None,
        plan_tasks: list[PlannedTask] | None = None,
    ) -> Any:
        """Run hierarchical manager execution with selected specialists."""
        crew = self.crew_for_tasks(plan_tasks) if plan_tasks else self.crew()
        prompt = coordinator_prompt or build_coordinator_prompt(
            prepared_request,
            compact_history,
            owner_context,
        )
        inputs = {
            "rewritten_query": prompt.rewritten_query,
            "resolved_references": prompt.resolved_references,
            "compact_history": prompt.compact_history,
            "owner_context": prompt.owner_context,
        }
        return crew.kickoff(inputs=inputs)
