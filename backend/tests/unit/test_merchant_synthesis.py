from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from agents.merchant.synthesis import synthesize_results
from services.merchant_execution_executor import SpecialistResult


def test_synthesis_requires_at_least_two_results():
    with pytest.raises(ValueError, match="at least 2"):
        synthesize_results("query", [SpecialistResult(capability="owner", instruction="a", status="completed", content="b")], MagicMock())


def test_synthesis_combines_successful_and_failed_capabilities(monkeypatch):
    mock_prompt = MagicMock()
    mock_prompt.compile.return_value = "compiled synthesis prompt"

    monkeypatch.setattr(
        "agents.merchant.synthesis.get_merchant_prompt",
        lambda key, label=None: mock_prompt,
    )

    mock_llm = MagicMock()
    mock_llm.model = "v-llm-v1-medium"
    mock_llm.call.return_value = "Combined synthesized answer"

    results = [
        SpecialistResult(capability="owner", instruction="Check owner", status="completed", content="Owner revenue is up 10%"),
        SpecialistResult(capability="policy", instruction="Check policy", status="failed", content="", error="no_tool_evidence"),
    ]

    answer = synthesize_results("How is my store doing under current policy?", results, mock_llm)
    assert answer == "Combined synthesized answer"
    mock_llm.call.assert_called_once_with("compiled synthesis prompt")
    mock_prompt.compile.assert_called_once()
    compiled_kwargs = mock_prompt.compile.call_args.kwargs
    assert "OWNER EVIDENCE" in compiled_kwargs["specialist_results"]
    assert "UNAVAILABLE / FAILED CAPABILITIES" in compiled_kwargs["specialist_results"]
