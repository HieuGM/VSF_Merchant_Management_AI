from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def test_lifespan_authenticates_instruments_and_shuts_down(monkeypatch):
    client = MagicMock()
    client.auth_check.return_value = True
    instrumentor = MagicMock()
    monkeypatch.setattr("app.main.get_client", lambda: client)
    monkeypatch.setattr("app.main.CrewAIInstrumentor", lambda: instrumentor)

    with TestClient(create_app()):
        pass

    client.auth_check.assert_called_once_with()
    instrumentor.instrument.assert_called_once_with(skip_dep_check=True)
    client.shutdown.assert_called_once_with()


def test_lifespan_rejects_failed_authentication(monkeypatch):
    client = MagicMock()
    client.auth_check.return_value = False
    monkeypatch.setattr("app.main.get_client", lambda: client)

    with pytest.raises(RuntimeError, match="Langfuse authentication failed"):
        with TestClient(create_app()):
            pass
