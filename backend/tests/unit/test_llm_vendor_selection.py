"""LLM vendor selection — auto-detect FPT (fast) vs NVIDIA NIM, with explicit override."""
from __future__ import annotations

import pytest

from core.settings import Settings

_FPT = dict(
    fpt_api_key="k", fpt_base_url="https://x/v1", fpt_model_deepseek="DeepSeek-V3"
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # database.connection calls load_dotenv() → the real .env (with FPT_*) leaks into
    # os.environ. Strip those so vendor-selection logic tests are deterministic.
    for k in (
        "FPT_API_KEY", "FPT_BASE_URL", "FPT_MODEL_DEEPSEEK", "FPT_MODEL_QWEN",
        "LLM_VENDOR", "NVIDIA_NIM_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)


def _settings(**kw) -> Settings:
    # `_env_file=None` + cleaned os.environ isolates the logic test from the real .env.
    return Settings(_env_file=None, **kw)


def test_auto_selects_fpt_when_configured():
    s = _settings(nvidia_nim_api_key="nim", **_FPT)
    assert s.fpt_configured is True
    assert s.active_llm_vendor == "fpt"
    assert s.llm_configured is True


def test_falls_back_to_nim_without_fpt():
    s = _settings(nvidia_nim_api_key="nim")
    assert s.fpt_configured is False
    assert s.active_llm_vendor == "nvidia_nim"
    assert s.llm_configured is True


def test_explicit_override_forces_vendor():
    # Force NIM even though FPT is fully configured.
    s = _settings(nvidia_nim_api_key="nim", llm_vendor="nvidia_nim", **_FPT)
    assert s.active_llm_vendor == "nvidia_nim"


def test_partial_fpt_config_not_selected():
    # Missing model → not considered configured → NIM.
    s = _settings(nvidia_nim_api_key="nim", fpt_api_key="k", fpt_base_url="https://x/v1")
    assert s.fpt_configured is False
    assert s.active_llm_vendor == "nvidia_nim"
