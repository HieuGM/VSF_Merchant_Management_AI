"""Dish-keyword search resolves via menu items, not exact cuisine (general fix).

Requires Postgres (skips when unreachable). A dish term ("phở") must find merchants that
sell it even though the DB stores cuisine as a broad category ("Món Việt"). Guards the
regression where "phở" was mapped to cuisine=Phở and returned 0.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from database.connection import engine
from tools.registry import registry


@pytest.fixture(autouse=True)
def _discover():
    if "merchant_search" not in registry.names():
        registry.auto_discover("tools.shared")
        registry.auto_discover("tools.customer")


def _require_db():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1;"))
    except OperationalError:
        pytest.skip("Postgres not reachable — integration test skipped.")


def test_dish_query_matches_via_menu():
    _require_db()
    out = registry.get("merchant_search").fn(query="phở", limit=10)
    # "phở" is a dish, cuisine is stored broad ("Món Việt") — must still find sellers.
    assert out["total"] > 0, "dish keyword should match merchants via name/menu"


def test_nearby_accepts_dish_query():
    _require_db()
    # nearby search must ACCEPT a dish keyword param (not force it into cuisine).
    out = registry.get("nearby_merchant_search").fn(
        lat=10.7769, lng=106.7009, radius_km=5, query="phở", limit=10
    )
    assert "merchants" in out and out["total"] >= 0  # shape + no crash
    # A keyword filters DOWN (subset), never adds results beyond the unfiltered nearby set.
    no_kw = registry.get("nearby_merchant_search").fn(
        lat=10.7769, lng=106.7009, radius_km=5, limit=10
    )
    assert out["total"] <= no_kw["total"]


def test_dish_not_confused_with_cuisine():
    _require_db()
    # Passing a dish name as cuisine (the old bug) yields few/none; as query it works.
    as_cuisine = registry.get("merchant_search").fn(cuisine="phở", limit=10)["total"]
    as_query = registry.get("merchant_search").fn(query="phở", limit=10)["total"]
    assert as_query >= as_cuisine
