"""Behavior tests for the H3 candidate-cell adapter."""

from services.geo.h3_index import H3CandidateIndex, haversine_km
from database.models import Merchant


def test_cells_for_radius_contains_origin_cell_and_neighbors():
    index = H3CandidateIndex(resolution=8)

    origin = index.cell_for(16.0544, 108.2022)
    cells = index.cells_for_radius(16.0544, 108.2022, 3.0)

    assert origin in cells
    assert len(cells) > 1


def test_cells_for_zero_radius_contains_only_origin_cell():
    index = H3CandidateIndex(resolution=8)

    assert index.cells_for_radius(16.0544, 108.2022, 0.0) == {
        index.cell_for(16.0544, 108.2022)
    }


def test_haversine_distance_is_zero_for_same_point():
    assert haversine_km(16.0544, 108.2022, 16.0544, 108.2022) == 0.0


def test_merchant_insert_populates_h3_cell_from_coordinates(db_session):
    merchant = Merchant(
        merchant_id="h3-auto-indexed",
        name="Auto Indexed Merchant",
        cuisine="Món Việt",
        city="Đà Nẵng",
        city_slug="da_nang",
        lat=16.0544,
        lng=108.2022,
    )
    db_session.add(merchant)
    db_session.flush()

    assert merchant.h3_index_6 == H3CandidateIndex(resolution=6).cell_for(16.0544, 108.2022)
    assert merchant.merchant_h3_cell == H3CandidateIndex(resolution=8).cell_for(16.0544, 108.2022)
    assert merchant.h3_index_9 == H3CandidateIndex(resolution=9).cell_for(16.0544, 108.2022)
