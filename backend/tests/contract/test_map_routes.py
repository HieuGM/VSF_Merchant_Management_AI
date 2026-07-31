"""Contract tests for developer-facing merchant map candidates."""
from __future__ import annotations

import pytest

from app.main import app
from core.dependencies import get_db_session
from database.models import Merchant


@pytest.fixture
def real_client(client, db_session):
    app.dependency_overrides[get_db_session] = lambda: db_session
    yield client
    app.dependency_overrides.clear()


def test_map_geojson_contains_owner_user_and_public_candidates(real_client, db_session):
    owner = Merchant(
        merchant_id="map-owner",
        name="Map Owner",
        cuisine="Món Việt",
        city="Map Test City",
        city_slug="map_test_city",
        lat=16.0544,
        lng=108.2022,
        is_active=True,
    )
    competitor = Merchant(
        merchant_id="map-competitor",
        name="Map Competitor",
        cuisine="Món Việt",
        city="Map Test City",
        city_slug="map_test_city",
        lat=16.055,
        lng=108.203,
        is_active=True,
    )
    db_session.add_all([owner, competitor])
    db_session.commit()

    response = real_client.get(
        "/api/v1/maps/merchants.geojson",
        params={"merchant_id": owner.merchant_id, "lat": 16.0544, "lng": 108.2022, "radius_km": 3},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    by_id = {
        feature["properties"].get("merchant_id"): feature
        for feature in payload["features"]
        if feature["properties"].get("merchant_id")
    }
    assert by_id[owner.merchant_id]["properties"]["role"] == "owner"
    assert by_id[competitor.merchant_id]["properties"]["role"] == "competitor"
    assert any(
        feature["properties"]["role"] == "user_location"
        for feature in payload["features"]
    )

    recommended_response = real_client.get(
        "/api/v1/maps/merchants.geojson",
        params={
            "merchant_id": owner.merchant_id,
            "lat": 16.0544,
            "lng": 108.2022,
            "radius_km": 3,
            "recommended_merchant_ids": competitor.merchant_id,
        },
    )
    recommended_feature = next(
        feature
        for feature in recommended_response.json()["features"]
        if feature["properties"].get("merchant_id") == competitor.merchant_id
    )
    assert recommended_feature["properties"]["role"] == "recommended"


def test_map_geojson_includes_retrieved_candidates_outside_the_h3_viewport(
    real_client,
    db_session,
):
    owner = Merchant(
        merchant_id="map-retrieved-owner",
        name="Retrieved Map Owner",
        cuisine="Món Việt",
        city="Map Test City",
        city_slug="map_test_city",
        lat=16.0544,
        lng=108.2022,
        is_active=True,
    )
    retrieved = Merchant(
        merchant_id="map-retrieved-far",
        name="Retrieved Candidate",
        cuisine="Món Nhật",
        city="Another City",
        city_slug="another_city",
        lat=21.0285,
        lng=105.8542,
        is_active=True,
    )
    db_session.add_all([owner, retrieved])
    db_session.commit()

    response = real_client.get(
        "/api/v1/maps/merchants.geojson",
        params={
            "merchant_id": owner.merchant_id,
            "lat": owner.lat,
            "lng": owner.lng,
            "radius_km": 1,
            "candidate_merchant_ids": retrieved.merchant_id,
            "recommended_merchant_ids": retrieved.merchant_id,
        },
    )

    assert response.status_code == 200
    feature = next(
        item
        for item in response.json()["features"]
        if item["properties"].get("merchant_id") == retrieved.merchant_id
    )
    assert feature["properties"]["role"] == "recommended"
