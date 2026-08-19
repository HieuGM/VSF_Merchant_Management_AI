from __future__ import annotations

import json
from typing import Any
from langfuse import get_client

from models.merchant_execution import PlannerDecision, parse_planner_decision
from services.mem0_service import MemoryHit
from services.merchant_prompts import get_merchant_prompt


def plan_request(
    query: str,
    memories: list[MemoryHit],
    owner_context: dict[str, Any],
    llm: Any,
    *,
    label: str | None = None,
) -> PlannerDecision:
    """Run single planner LLM call and return strictly validated PlannerDecision."""
    client = get_client()
    prompt = get_merchant_prompt("planner", label=label)

    memory_list = [hit.memory for hit in memories if hit.memory]
    memory_context_str = json.dumps(memory_list, ensure_ascii=False)
    owner_context_str = json.dumps(owner_context, ensure_ascii=False, sort_keys=True)

    compiled_prompt = prompt.compile(
        query=query,
        memory_context=memory_context_str,
        owner_context=owner_context_str,
    )

    with client.start_as_current_observation(
        name="planner",
        as_type="generation",
        input={
            "query": query,
            "memory_context": memory_list,
            "owner_context": owner_context,
        },
        model=getattr(llm, "model", None),
        prompt=prompt,
    ) as observation:
        if hasattr(llm, "call"):
            raw_output = llm.call(compiled_prompt)
        elif callable(llm):
            raw_output = llm(compiled_prompt)
        else:
            raw_output = str(llm)

        if hasattr(raw_output, "content"):
            raw_text = raw_output.content
        else:
            raw_text = str(raw_output)

        decision = parse_planner_decision(raw_text)
        observation.update(output=decision.model_dump())
        return decision
