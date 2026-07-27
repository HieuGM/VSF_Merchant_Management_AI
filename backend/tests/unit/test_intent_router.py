"""Unit tests for Intent Classification and Flow Dispatcher."""
from __future__ import annotations

import json
from unittest.mock import MagicMock
from flows.merchant_flow import classify_intent, MerchantAdvisorCrew
import flows.merchant_flow as merchant_flow_module


def test_classify_intent_via_llm(monkeypatch):
    class MockLLM:
        def __init__(self, returned_intent: str):
            self._returned = returned_intent

        def call(self, messages):
            return MagicMock(content=json.dumps({"intent": self._returned}))

    # Test search intent via LLM
    monkeypatch.setattr(merchant_flow_module, "get_configured_llm", lambda tier="large": MockLLM("search"))
    assert classify_intent("Tìm danh sách quán trà sữa hot nhất") == "search"

    # Test benchmark intent via LLM
    monkeypatch.setattr(merchant_flow_module, "get_configured_llm", lambda tier="large": MockLLM("benchmark"))
    assert classify_intent("So sánh đối thủ xung quanh") == "benchmark"

    # Test weakness_explanation intent via LLM
    monkeypatch.setattr(merchant_flow_module, "get_configured_llm", lambda tier="large": MockLLM("weakness_explanation"))
    assert classify_intent("Tại sao điểm chẩn đoán sụt giảm") == "weakness_explanation"


def test_classify_intent_fallback_without_llm(monkeypatch):
    monkeypatch.setattr(merchant_flow_module, "get_configured_llm", lambda tier="large": None)

    assert classify_intent("Tìm danh sách quán trà sữa hot nhất") == "search"
    assert classify_intent("So sánh vị thế đối thủ xung quanh quán 5km") == "benchmark"
    assert classify_intent("Tại sao điểm chẩn đoán sụt giảm, cần đề xuất cải thiện") == "weakness_explanation"
    assert classify_intent("Xem metrics vận hành và khiếu nại complaint của quán") == "ops_analysis"
    assert classify_intent("Xin chào bạn") == "general_chat"


def test_build_crew_for_intent_assembly():
    crew_builder = MerchantAdvisorCrew()

    crew_search = crew_builder.build_crew_for_intent("search")
    assert len(crew_search.agents) >= 2

    crew_benchmark = crew_builder.build_crew_for_intent("benchmark")
    assert len(crew_benchmark.agents) >= 2

    crew_weakness = crew_builder.build_crew_for_intent("weakness_explanation")
    assert len(crew_weakness.agents) >= 4

    crew_ops = crew_builder.build_crew_for_intent("ops_analysis")
    assert len(crew_ops.agents) >= 2

    crew_general = crew_builder.build_crew_for_intent("general_chat")
    assert len(crew_general.agents) == 1
