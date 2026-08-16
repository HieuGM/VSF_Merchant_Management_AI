from __future__ import annotations

import logging

import pytest
from models.merchant_input import PreparedRequest

from agents.merchant.input_analyzer_prompt import build_bounded_prompt
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


class FailingAnalyzer:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    def call(self, _prompt: str) -> str:
        self.calls += 1
        raise self.error


@pytest.fixture(autouse=True)
def remote_prompts(monkeypatch):
    def compile_prompt(key: str, **variables: str):
        return f"{key}\n{variables}", object()

    monkeypatch.setattr(
        "agents.merchant.input_analyzer_prompt.compile_merchant_prompt",
        compile_prompt,
    )
    monkeypatch.setattr(
        "services.merchant_input_preparation.propagate_attributes",
        lambda **_kwargs: __import__("contextlib").nullcontext(),
    )


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
        '"scope_candidate":"allowed","missing_context":[]}'
    )

    result = prepare(llm)

    assert result.rewritten_query == "So sánh review 'quanh đây'"
    assert result.scope_candidate == "allowed"
    assert len(llm.calls) == 1


def test_analyzer_accepts_native_structured_response_without_repair():
    llm = FakeAnalyzer(
        PreparedRequest(
            rewritten_query="Tôi muốn code",
            scope_candidate="out_of_scope",
        )
    )

    result = InputPreparationService(llm=llm).prepare(
        raw_query="Tôi muốn code",
        history=[],
        session_state={},
        owner_context={},
    )

    assert result.scope_candidate == "out_of_scope"
    assert len(llm.calls) == 1


def test_analyzer_accepts_fenced_repair_aliases():
    llm = FakeAnalyzer(
        "not-json",
        "```json\n"
        '{"rewritten_query":"So sánh review","scope":"allowed",'
        '"missing_context":[]}\n```',
    )

    result = prepare(llm)

    assert result.scope_candidate == "allowed"
    assert len(llm.calls) == 2


def test_analyzer_failure_trace_keeps_sanitized_raw_and_repair_outputs():
    traces: list[dict] = []
    llm = FakeAnalyzer("invalid api_key=secret-value", "still invalid")

    with pytest.raises(InputPreparationError, match="schema_repair_failed"):
        prepare(llm, traces)

    assert traces[0]["parse_result"] == "schema_repair_failed"
    assert traces[0]["raw_model_output"] == "invalid api_key=<redacted>"
    assert traces[0]["repair_model_output"] == "still invalid"


def test_trace_callback_failure_is_logged_without_changing_valid_result(caplog):
    llm = FakeAnalyzer(
        '{"rewritten_query":"Hello","resolved_references":[],'
        '"scope_candidate":"allowed","missing_context":[]}'
    )
    service = InputPreparationService(
        llm=llm,
        trace_callback=lambda *_args: (_ for _ in ()).throw(
            RuntimeError("secret analyzer trace payload")
        ),
    )

    with caplog.at_level(
        logging.WARNING,
        logger="services.merchant_input_preparation",
    ):
        result = service.prepare(
            raw_query="Hello",
            history=[],
            session_state={},
            owner_context={},
        )

    assert result.rewritten_query == "Hello"
    assert "input_analyzer_trace_callback_failed" in caplog.text
    assert "secret analyzer trace payload" not in caplog.text


def test_provider_prompt_injection_error_becomes_stable_block_without_retry():
    provider_error = RuntimeError(
        {"detail": {"error": "prompt_injection_detected", "categories": ["jb_word"]}}
    )
    wrapped_error = RuntimeError("OpenAI API call failed")
    wrapped_error.__cause__ = provider_error
    llm = FailingAnalyzer(wrapped_error)

    with pytest.raises(InputPreparationError, match="^prompt_injection_blocked$"):
        prepare(llm)

    assert llm.calls == 1


def test_unrelated_provider_error_remains_provider_call_failed():
    llm = FailingAnalyzer(RuntimeError("provider unavailable"))

    with pytest.raises(InputPreparationError, match="^provider_call_failed$"):
        prepare(llm)

    assert llm.calls == 1


@pytest.mark.parametrize(
    "provider_error",
    [
        RuntimeError({"detail": {"error": "prompt_injection_detected_timeout"}}),
        RuntimeError("request mentioned prompt_injection_detected"),
    ],
)
def test_prompt_injection_near_matches_remain_provider_failures(provider_error):
    llm = FailingAnalyzer(provider_error)

    with pytest.raises(InputPreparationError, match="^provider_call_failed$"):
        prepare(llm)


def test_bounded_prompt_compiles_bounded_variables():
    prompt = build_bounded_prompt(
        raw_query="Hello",
        history=[],
        session_state={},
        owner_context={},
    )

    assert prompt.startswith("INPUT_ANALYZER_PROMPT")
    assert "Hello" in prompt


def test_bounded_prompt_overrides_stale_remote_execution_fields(monkeypatch):
    monkeypatch.setattr(
        "agents.merchant.input_analyzer_prompt.compile_merchant_prompt",
        lambda _key, **_variables: ("Return proposed_outcome and route.", object()),
    )

    prompt = build_bounded_prompt(
        raw_query="Tìm tài liệu cần thiết để đăng ký merchant",
        history=[],
        session_state={},
        owner_context={},
    )

    assert '"rewritten_query"' in prompt
    assert "Do not output proposed_outcome" in prompt
