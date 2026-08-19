import logging
import ssl
from unittest.mock import MagicMock

import httpx
import pytest
import requests
from fastapi.testclient import TestClient

from app.main import create_app, initialize_langfuse


def _patch_langfuse_dependencies(monkeypatch, client):
    langfuse = MagicMock(return_value=client)
    settings = MagicMock(
        langfuse_public_key="pk-test",
        langfuse_secret_key="sk-test",
        langfuse_base_url="https://jp.cloud.langfuse.com",
    )
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    monkeypatch.setattr("app.main.sync_langfuse_env", lambda settings: None)
    monkeypatch.setattr("app.main.Langfuse", langfuse)
    return langfuse


def test_lifespan_authenticates_and_shuts_down(monkeypatch):
    client = MagicMock()
    client.auth_check.return_value = True
    _patch_langfuse_dependencies(monkeypatch, client)
    monkeypatch.setenv("LANGFUSE_INSECURE_SSL", "false")

    with TestClient(create_app()):
        pass

    client.auth_check.assert_called_once_with()
    client.shutdown.assert_called_once_with()


def test_lifespan_rejects_failed_authentication(monkeypatch):
    client = MagicMock()
    client.auth_check.return_value = False
    _patch_langfuse_dependencies(monkeypatch, client)
    monkeypatch.setenv("LANGFUSE_INSECURE_SSL", "false")

    with pytest.raises(RuntimeError, match="Langfuse authentication failed"):
        with TestClient(create_app()):
            pass


def test_secure_langfuse_uses_default_otel_tls_verification(monkeypatch):
    client = MagicMock()
    client.auth_check.return_value = True
    langfuse = _patch_langfuse_dependencies(monkeypatch, client)
    monkeypatch.setenv("LANGFUSE_INSECURE_SSL", "false")

    initialize_langfuse()

    kwargs = langfuse.call_args.kwargs
    assert "span_exporter" not in kwargs
    assert isinstance(kwargs["httpx_client"], httpx.Client)
    assert (
        kwargs["httpx_client"]._transport._pool._ssl_context.verify_mode
        == ssl.CERT_REQUIRED
    )


def test_insecure_langfuse_scopes_disabled_tls_to_its_clients(
    monkeypatch, caplog
):
    client = MagicMock()
    client.auth_check.return_value = True
    langfuse = _patch_langfuse_dependencies(monkeypatch, client)
    monkeypatch.setenv("LANGFUSE_INSECURE_SSL", "true")

    with caplog.at_level(logging.WARNING):
        initialize_langfuse()

    kwargs = langfuse.call_args.kwargs
    exporter = kwargs["span_exporter"]
    response = requests.Response()
    response.status_code = 200
    exporter._session.send = MagicMock(return_value=response)
    exporter._session.post(exporter._endpoint, verify=True)

    assert exporter._session.send.call_args.kwargs["verify"] is False
    assert requests.Session().verify is True
    assert (
        httpx.Client()._transport._pool._ssl_context.verify_mode
        == ssl.CERT_REQUIRED
    )
    assert "TLS certificate verification is disabled" in caplog.text


def test_insecure_otel_exporter_uses_langfuse_timeout(monkeypatch):
    client = MagicMock()
    client.auth_check.return_value = True
    langfuse = _patch_langfuse_dependencies(monkeypatch, client)
    monkeypatch.setenv("LANGFUSE_INSECURE_SSL", "true")
    monkeypatch.setenv("LANGFUSE_TIMEOUT", "30")

    initialize_langfuse()

    assert langfuse.call_args.kwargs["span_exporter"]._timeout == 30.0
