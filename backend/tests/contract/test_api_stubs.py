"""Boot smoke test + frozen API surface (health + stub 501s)."""
from __future__ import annotations


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["redis"] == "ok"  # in-memory adapter
    assert "database" in body
    assert "llm_configured" in body


def test_stub_routes_return_501(client):
    for method, path in [
        ("get", "/api/v1/merchants/68814/profile"),
        ("post", "/api/v1/agent/merchant/chat"),
        ("post", "/api/v1/users/u1/events"),
        ("get", "/api/v1/maps/merchants.geojson"),
        ("get", "/api/v1/agent/runs/trace_1"),
    ]:
        resp = getattr(client, method)(path)
        assert resp.status_code == 501, f"{method} {path}"
        assert resp.json()["error"]["details"]["phase0_stub"] is True


def test_user_profile_endpoints_implemented(client):
    """phase-01: GET/PATCH /profile are wired (no longer 501 stubs).

    GET unknown user → 404 (implemented, no row — needs DB). PATCH with an empty body →
    400 (no fields, no DB write) proving the route parses ProfilePatchRequest + the
    dev-only IDOR guard admits the request."""
    resp = client.get("/api/v1/users/u1/profile")
    assert resp.status_code == 404, "GET /profile should be implemented (404 for unknown user), not 501"

    resp = client.patch("/api/v1/users/u1/profile", json={})
    assert resp.status_code == 400, "PATCH /profile with no fields → 400 (implemented)"


def test_profile_patch_rejects_unknown_field(client):
    """ProfilePatchRequest uses extra=forbid → an unknown body key (e.g. a spoofed
    ``user_id``) is rejected with 422 rather than silently dropped (invariant #5)."""
    resp = client.patch("/api/v1/users/u1/profile", json={"user_id": "someone_else"})
    assert resp.status_code == 422, "unknown field must be rejected (extra=forbid)"


def test_profile_write_blocked_in_production(client, monkeypatch):
    """The IDOR guard (require_dev_only) MUST 403 profile writes in production until real
    auth lands. Dev (default environment) admits — covered by the implemented-endpoint
    test above (PATCH reaches the 400 no-fields path, i.e. the guard passed)."""
    from types import SimpleNamespace

    monkeypatch.setattr(
        "core.dependencies.get_settings",
        lambda: SimpleNamespace(environment="production"),
    )
    resp = client.patch("/api/v1/users/u1/profile", json={"budget_level": "student"})
    assert resp.status_code == 403, "profile PATCH must be 403 in production (IDOR guard)"


def test_merchant_search_endpoint_implemented(client):
    """Test that /api/v1/merchants/search returns 200 (implemented, not a stub)."""
    resp = client.get("/api/v1/merchants/search")
    assert resp.status_code == 200, "Search endpoint should return 200"
    body = resp.json()
    assert "trace_id" in body
    assert "merchants" in body
    assert "cache_status" in body


def test_customer_chat_endpoint_implemented(client):
    """Customer chat is wired (not a 501 stub). An empty body → 422 validation error,
    proving the route parses CustomerChatRequest without invoking the crew (no network)."""
    resp = client.post("/api/v1/agent/customer/chat", json={})
    assert resp.status_code == 422, "Chat endpoint should validate the request body"


def test_request_id_header_present(client):
    resp = client.get("/health")
    assert resp.headers.get("X-Request-ID")
