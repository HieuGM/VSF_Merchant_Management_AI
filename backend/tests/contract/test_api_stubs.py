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
        ("post", "/api/v1/agent/customer/chat"),
        ("get", "/api/v1/users/u1/profile"),
        ("post", "/api/v1/users/u1/events"),
    ]:
        resp = getattr(client, method)(path)
        assert resp.status_code == 501, f"{method} {path}"
        assert resp.json()["error"]["details"]["phase0_stub"] is True


def test_merchant_search_endpoint_implemented(client):
    """Test that /api/v1/merchants/search returns 200 (implemented, not a stub)."""
    resp = client.get("/api/v1/merchants/search")
    assert resp.status_code == 200, "Search endpoint should return 200"
    body = resp.json()
    assert "trace_id" in body
    assert "merchants" in body
    assert "cache_status" in body


def test_trace_endpoint_implemented(client):
    """Test that /api/v1/agent/runs/{trace_id} returns 404 for unknown trace (implemented in Task 4)."""
    resp = client.get("/api/v1/agent/runs/non_existent_trace")
    assert resp.status_code == 404


def test_merchant_profile_endpoint_implemented(client):
    """Test that /api/v1/merchants/{id}/profile returns 404 for non-existent merchant (implemented in Task 5)."""
    resp = client.get("/api/v1/merchants/non_existent_merchant/profile")
    assert resp.status_code == 404


def test_request_id_header_present(client):
    resp = client.get("/health")
    assert resp.headers.get("X-Request-ID")
