import os

from core.settings import Settings, sync_langfuse_env


def test_langfuse_env_variables_sync(monkeypatch):
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    settings = Settings(
        langfuse_secret_key="secret",
        langfuse_public_key="public",
        langfuse_base_url="https://example.test",
        environment="test",
    )
    sync_langfuse_env(settings)
    assert os.environ.get("LANGFUSE_SECRET_KEY") == settings.langfuse_secret_key
    assert os.environ.get("LANGFUSE_PUBLIC_KEY") == settings.langfuse_public_key
    assert os.environ.get("LANGFUSE_BASE_URL") == settings.langfuse_base_url
    assert os.environ.get("LANGFUSE_TRACING_ENVIRONMENT") == "test"
    assert "LANGFUSE_HOST" not in os.environ
