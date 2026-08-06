from __future__ import annotations

import pytest

from agents.merchant.input_analyzer_prompt import SYSTEM_PROMPT
from services.merchant_input_preparation import (
    InputPreparationError,
    InputPreparationService,
)


class FakeAnalyzer:
    max_tokens = 3_000

    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.calls: list[str] = []

    def call(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.responses.pop(0)


def prepare(llm: FakeAnalyzer, traces: list[dict] | None = None):
    return InputPreparationService(
        llm=llm,
        trace_callback=(
            (lambda _event, payload: traces.append(payload)) if traces is not None else None
        ),
    ).prepare(
        raw_query="so sánh reviews quanh đây",
        history=[],
        session_state={"merchant_id": "9634"},
        owner_context={"merchant_id": "9634", "has_stored_location": True},
    )


def test_analyzer_accepts_gemini_escaped_apostrophe_without_repair_call():
    llm = FakeAnalyzer(
        '{"rewritten_query":"So sánh review \\\'quanh đây\\\'",'
        '"scope_candidate":"allowed","missing_context":[],'
        '"proposed_outcome":"coordinate"}'
    )

    result = prepare(llm)

    assert result.rewritten_query == "So sánh review 'quanh đây'"
    assert result.scope_candidate == "allowed"
    assert len(llm.calls) == 1


def test_analyzer_accepts_fenced_repair_aliases():
    llm = FakeAnalyzer(
        "not-json",
        "```json\n"
        '{"rewritten_query":"So sánh review","scope":"allowed",'
        '"missing_context":[],"outcome":"coordinate"}\n```',
    )

    result = prepare(llm)

    assert result.scope_candidate == "allowed"
    assert result.proposed_outcome == "coordinate"
    assert len(llm.calls) == 2


def test_analyzer_failure_trace_keeps_sanitized_raw_and_repair_outputs():
    traces: list[dict] = []
    llm = FakeAnalyzer("invalid api_key=secret-value", "still invalid")

    with pytest.raises(InputPreparationError, match="schema_repair_failed"):
        prepare(llm, traces)

    assert traces[0]["parse_result"] == "schema_repair_failed"
    assert traces[0]["raw_model_output"] == "invalid api_key=<redacted>"
    assert traces[0]["repair_model_output"] == "still invalid"


def test_analyzer_prompt_preserves_operation_and_requires_real_context_evidence():
    assert "Preserve the user's operation exactly" in SYSTEM_PROMPT
    assert "Only assistant-role" in SYSTEM_PROMPT
    assert "record the absence" in SYSTEM_PROMPT
    assert "conversational-history" in SYSTEM_PROMPT
