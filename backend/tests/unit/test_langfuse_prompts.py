from unittest.mock import MagicMock
import pytest

from core.settings import get_settings


def test_prompt_registry_uses_namespace_label_and_ttl(monkeypatch):
    from services import merchant_prompts

    client = MagicMock()
    prompt = MagicMock()
    prompt.compile.return_value = "compiled"
    client.get_prompt.return_value = prompt
    monkeypatch.setattr(merchant_prompts, "get_client", lambda: client)
    get_settings.cache_clear()

    text, linked_prompt = merchant_prompts.compile_merchant_prompt(
        "planner", query="xin chao"
    )

    client.get_prompt.assert_called_once_with(
        "merchant/planner",
        label="production",
        cache_ttl_seconds=60,
    )
    prompt.compile.assert_called_once_with(query="xin chao")
    assert (text, linked_prompt) == ("compiled", prompt)


def test_prompt_registry_has_no_fallback(monkeypatch):
    from services import merchant_prompts

    client = MagicMock()
    client.get_prompt.side_effect = RuntimeError("unavailable")
    monkeypatch.setattr(merchant_prompts, "get_client", lambda: client)

    with pytest.raises(RuntimeError, match="unavailable"):
        merchant_prompts.get_merchant_prompt("planner")


def test_unknown_prompt_key_raises_key_error():
    from services import merchant_prompts
    with pytest.raises(KeyError):
        merchant_prompts.get_merchant_prompt("unknown_key")
