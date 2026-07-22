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
        ("post", "/api/v1/agent/customer/chat"),
        ("post", "/api/v1/agent/merchant/chat"),
        ("get", "/api/v1/users/u1/profile"),
        ("post", "/api/v1/users/u1/events"),
        ("get", "/api/v1/maps/merchants.geojson"),
        ("get", "/api/v1/agent/runs/trace_1"),
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


def test_request_id_header_present(client):
    resp = client.get("/health")
    assert resp.headers.get("X-Request-ID")
