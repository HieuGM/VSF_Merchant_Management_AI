from __future__ import annotations

from typing import Any
from langfuse import get_client

from services.merchant_prompts import get_merchant_prompt


def synthesize_results(
    query: str,
    results: list[Any],
    llm: Any,
    *,
    label: str | None = None,
) -> str:
    """Synthesize results from multiple specialists into one cohesive answer."""
    if len(results) < 2:
        raise ValueError(f"synthesis requires at least 2 specialist results, got {len(results)}")

    client = get_client()
    prompt = get_merchant_prompt("synthesis", label=label)

    # Format specialist results
    sections = []
    failed_caps = []
    for res in results:
        cap = getattr(res, "capability", "unknown")
        status = getattr(res, "status", "completed")
        content = getattr(res, "content", "")
        if status == "completed" and content:
            sections.append(f"[{cap.upper()} EVIDENCE]\n{content}")
        else:
            failed_caps.append(cap)

    if failed_caps:
        sections.append(f"[UNAVAILABLE / FAILED CAPABILITIES]\n{', '.join(failed_caps)}")

    specialist_results_text = "\n\n".join(sections)
    compiled_prompt = prompt.compile(
        query=query,
        specialist_results=specialist_results_text,
    )

    with client.start_as_current_observation(
        name="synthesis",
        as_type="generation",
        input={
            "query": query,
            "specialist_results": specialist_results_text,
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
            answer = raw_output.content.strip()
        else:
            answer = str(raw_output).strip()

        if not answer:
            raise ValueError("Synthesis returned empty answer")

        observation.update(output=answer)
        return answer
