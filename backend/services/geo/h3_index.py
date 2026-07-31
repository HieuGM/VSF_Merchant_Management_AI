"""H3 cell selection for bounded nearby-merchant candidate queries."""
from __future__ import annotations

from dataclasses import dataclass
from math import asin, ceil, cos, radians, sin, sqrt

import h3


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return straight-line distance between two WGS84 points."""
    earth_radius_km = 6371.0088
    lat1_rad, lat2_rad = radians(lat1), radians(lat2)
    delta_lat = radians(lat2 - lat1)
    delta_lng = radians(lng2 - lng1)
    haversine = (
        sin(delta_lat / 2) ** 2
        + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lng / 2) ** 2
    )
    return 2 * earth_radius_km * asin(sqrt(haversine))


@dataclass(frozen=True)
class H3CandidateIndex:
    """Convert coordinates and an approximate radius into H3 candidate cells.

    This adapter intentionally returns a conservative candidate set.  Exact
    routing or spatial distance ranking belongs to a later dedicated adapter,
    not to the retrieval query itself.
    """

    resolution: int = 8

    def cell_for(self, lat: float, lng: float) -> str:
        return h3.latlng_to_cell(lat, lng, self.resolution)

    def cells_for_radius(self, lat: float, lng: float, radius_km: float) -> set[str]:
        if radius_km < 0:
            raise ValueError("radius_km must be non-negative")

        origin = self.cell_for(lat, lng)
        return set(h3.grid_disk(origin, self.ring_count(radius_km)))

    def ring_count(self, radius_km: float) -> int:
        """Return enough rings to include cells that can overlap the radius."""
        if radius_km < 0:
            raise ValueError("radius_km must be non-negative")
        if radius_km == 0:
            return 0

        edge_km = h3.average_hexagon_edge_length(self.resolution, unit="km")
        center_spacing_km = sqrt(3) * edge_km
        return ceil((radius_km + edge_km) / center_spacing_km)
