"""Tests for H3-bounded merchant repository queries."""
from __future__ import annotations

from database.models import Merchant
from repositories.merchant_repository import MerchantRepository
from services.geo.h3_index import H3CandidateIndex


def test_nearby_candidates_filter_on_h3_cells(db_session):
    index = H3CandidateIndex()
    near = Merchant(
        merchant_id="h3-near",
        name="H3 Nearby",
        cuisine="H3 Repository Cuisine",
        city="Đà Nẵng",
        city_slug="da_nang",
        lat=16.055,
        lng=108.203,
        merchant_h3_cell=index.cell_for(16.055, 108.203),
        is_active=True,
    )
    far = Merchant(
        merchant_id="h3-far",
        name="H3 Far Away",
        cuisine="H3 Repository Cuisine",
        city="Đà Nẵng",
        city_slug="da_nang",
        lat=16.20,
        lng=108.20,
        merchant_h3_cell=index.cell_for(16.20, 108.20),
        is_active=True,
    )
    db_session.add_all([near, far])
    db_session.commit()

    candidates = MerchantRepository(db_session).find_nearby_candidates(
        lat=16.0544,
        lng=108.2022,
        radius_km=3.0,
        cuisine="H3 Repository Cuisine",
    )

    candidate_ids = {merchant.merchant_id for merchant in candidates}
    assert near.merchant_id in candidate_ids
    assert far.merchant_id not in candidate_ids


def test_general_search_applies_h3_constraint_before_query_execution(db_session):
    index = H3CandidateIndex()
    near = Merchant(
        merchant_id="h3-search-repository-near",
        name="H3 Repository Search Nearby",
        cuisine="H3 Repository Search Cuisine",
        city="Đà Nẵng",
        city_slug="da_nang",
        lat=16.055,
        lng=108.203,
        merchant_h3_cell=index.cell_for(16.055, 108.203),
        is_active=True,
    )
    far = Merchant(
        merchant_id="h3-search-repository-far",
        name="H3 Repository Search Far",
        cuisine="H3 Repository Search Cuisine",
        city="Đà Nẵng",
        city_slug="da_nang",
        lat=16.20,
        lng=108.20,
        merchant_h3_cell=index.cell_for(16.20, 108.20),
        is_active=True,
    )
    db_session.add_all([near, far])
    db_session.commit()

    merchants = MerchantRepository(db_session).search_merchants(
        cuisine="H3 Repository Search Cuisine",
        lat=16.0544,
        lng=108.2022,
        radius_km=3.0,
    )

    assert [merchant.merchant_id for merchant in merchants] == [near.merchant_id]


def test_nearby_candidates_expand_from_h3_9_to_h3_6_when_empty(db_session):
    expanded = Merchant(
        merchant_id="h3-repository-expanded",
        name="H3 Repository Expanded",
        cuisine="Adaptive H3 Cuisine",
        city="Đà Nẵng",
        city_slug="da_nang",
        lat=16.105,
        lng=108.2022,
        is_active=True,
    )
    db_session.add(expanded)
    db_session.commit()

    candidates = MerchantRepository(db_session).find_nearby_candidates(
        lat=16.0544,
        lng=108.2022,
        radius_km=2.0,
        cuisine="Adaptive H3 Cuisine",
    )

    assert [merchant.merchant_id for merchant in candidates] == [
        expanded.merchant_id
    ]
