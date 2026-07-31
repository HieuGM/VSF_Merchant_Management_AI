"""Contract for the merchant-owner choices exposed to the demo UI."""
from __future__ import annotations

from app.main import app
from core.dependencies import get_db_session
from database.models import Merchant


def test_demo_targets_endpoint_returns_only_active_demo_merchants(client, db_session):
    db_session.add_all(
        [
            Merchant(
                merchant_id="demo-active",
                name="Demo Active",
                cuisine="Món Việt",
                city="TP. HCM",
                city_slug="tp_hcm",
                is_active=True,
                is_demo_target=True,
            ),
            Merchant(
                merchant_id="demo-inactive",
                name="Demo Inactive",
                cuisine="Món Việt",
                city="TP. HCM",
                city_slug="tp_hcm",
                is_active=False,
                is_demo_target=True,
            ),
            Merchant(
                merchant_id="regular-active",
                name="Regular Active",
                cuisine="Món Việt",
                city="TP. HCM",
                city_slug="tp_hcm",
                is_active=True,
                is_demo_target=False,
            ),
        ]
    )
    db_session.commit()
    app.dependency_overrides[get_db_session] = lambda: db_session

    try:
        response = client.get("/api/v1/merchants/demo-targets")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    merchants = response.json()["merchants"]
    by_id = {merchant["merchant_id"]: merchant for merchant in merchants}
    assert by_id["demo-active"] == {
        "merchant_id": "demo-active",
        "name": "Demo Active",
        "city": "TP. HCM",
        "cuisine": "Món Việt",
    }
    assert "demo-inactive" not in by_id
    assert "regular-active" not in by_id
