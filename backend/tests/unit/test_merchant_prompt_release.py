from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock
import pytest


def _load_script_module():
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "langfuse" / "push_merchant_prompts.py"
    spec = importlib.util.spec_from_file_location("push_merchant_prompts", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_merchant_prompts_release_definitions():
    mod = _load_script_module()
    expected_prompts = {
        "merchant/planner",
        "merchant/specialist-owner",
        "merchant/specialist-market",
        "merchant/specialist-policy",
        "merchant/specialist-review",
        "merchant/specialist-cohort",
        "merchant/synthesis",
    }
    assert set(mod.PROMPTS.keys()) == expected_prompts


def test_push_prompts_creates_all_with_candidate_label(monkeypatch):
    mod = _load_script_module()
    mock_client = MagicMock()
    monkeypatch.setattr(mod, "get_langfuse_client", lambda: mock_client)

    mod.push_prompts(label="candidate")
    assert mock_client.create_prompt.call_count == 7
    mock_client.flush.assert_called_once()


def test_promote_production_updates_labels(monkeypatch):
    mod = _load_script_module()
    mock_client = MagicMock()
    mock_prompt = MagicMock()
    mock_prompt.name = "merchant/planner"
    mock_prompt.version = 2
    mock_client.get_prompt.return_value = mock_prompt
    monkeypatch.setattr(mod, "get_langfuse_client", lambda: mock_client)

    mod.promote_production(source_label="candidate")
    assert mock_client.update_prompt.call_count == 7
    mock_client.flush.assert_called_once()
