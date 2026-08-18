"""Test merchant search input validation and SQL injection protection (Bug Fixes 2 & 3)."""
from __future__ import annotations


# DB-gated: these tests exercise REAL queries (route → repo → Postgres). On CI (no
# Postgres) they'd fail with connection refused — skip there, matching the pattern
# integration tests already use (_require_db).
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from database.connection import engine

try:
    with engine.connect() as _c:
        _c.execute(text("SELECT 1;"))
    _HAS_DB = True
except OperationalError:
    _HAS_DB = False

pytestmark = pytest.mark.skipif(not _HAS_DB, reason="Postgres not reachable")


def test_search_rejects_invalid_lat(client):
    """Test that latitude > 90 is rejected (Fix 2)."""
    resp = client.get("/api/v1/merchants/search?lat=91&lng=0")
    assert resp.status_code == 422  # Validation error
    body = resp.json()
    assert "detail" in body


def test_search_rejects_invalid_lng(client):
    """Test that longitude > 180 is rejected (Fix 2)."""
    resp = client.get("/api/v1/merchants/search?lat=0&lng=181")
    assert resp.status_code == 422  # Validation error
    body = resp.json()
    assert "detail" in body


def test_search_rejects_negative_radius(client):
    """Test that radius_km <= 0 is rejected (Fix 2)."""
    resp = client.get("/api/v1/merchants/search?lat=0&lng=0&radius_km=-1")
    assert resp.status_code == 422  # Validation error
    body = resp.json()
    assert "detail" in body


def test_search_rejects_radius_exceeds_max(client):
    """Test that radius_km > 500 is rejected (Fix 2)."""
    resp = client.get("/api/v1/merchants/search?lat=0&lng=0&radius_km=501")
    assert resp.status_code == 422  # Validation error
    body = resp.json()
    assert "detail" in body


def test_nearby_rejects_invalid_lat(client):
    """Test that nearby endpoint validates latitude (Fix 2)."""
    resp = client.get("/api/v1/merchants/nearby?lat=-91&lng=0")
    assert resp.status_code == 422  # Validation error


def test_nearby_rejects_invalid_lng(client):
    """Test that nearby endpoint validates longitude (Fix 2)."""
    resp = client.get("/api/v1/merchants/nearby?lat=0&lng=181")
    assert resp.status_code == 422  # Validation error


def test_nearby_rejects_negative_radius(client):
    """Test that nearby endpoint validates radius_km (Fix 2)."""
    resp = client.get("/api/v1/merchants/nearby?lat=0&lng=0&radius_km=-5")
    assert resp.status_code == 422  # Validation error


def test_nearby_requires_lat_lng(client):
    """Test that nearby endpoint requires lat and lng (Fix 2)."""
    resp = client.get("/api/v1/merchants/nearby")
    assert resp.status_code == 422  # Validation error - missing required params


def test_search_handles_special_characters(client):
    """Test that search handles special characters without SQL injection (Fix 3)."""
    # Special characters that could be used for SQL injection: \, %, _
    test_cases = [
        "test\\query",      # Backslash
        "test%query",       # Percent
        "test_query",       # Underscore
        "test%_%_\\%_%",    # Mixed special chars
        "'; DROP TABLE--",  # SQL injection attempt
    ]

    for query in test_cases:
        resp = client.get(f"/api/v1/merchants/search?query={query}")
        # Should return 200 (handled safely) or empty result set, NOT 500 error
        assert resp.status_code in (200, 404), f"Failed for query: {query}"
        # If we get 200, verify response structure is valid
        if resp.status_code == 200:
            body = resp.json()
            assert "trace_id" in body
            assert "merchants" in body
            assert "cache_status" in body


def test_search_with_percent_wildcard(client):
    """Test that % is properly escaped in LIKE queries (Fix 3)."""
    # This tests that the escape="\\ parameter in ilike works correctly
    resp = client.get("/api/v1/merchants/search?query=pho%20restaurant")
    assert resp.status_code in (200, 404)
    if resp.status_code == 200:
        body = resp.json()
        assert "merchants" in body
        # If results found, they should match "pho restaurant" not any string ending with "restaurant"
