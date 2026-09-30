"""Geospatial helpers.

SQLite has no spatial support, so distance is computed with the haversine
formula in Python after a cheap bounding-box prefilter. On PostgreSQL+PostGIS
replace `bounding_box` / `haversine_km` usage in the retrieval service with
`ST_DWithin` on a `geography(Point,4326)` column - nothing else changes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class GeoPoint:
    latitude: float
    longitude: float


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, a)))


def bounding_box(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """(min_lat, max_lat, min_lon, max_lon) covering `radius_km` around a point.

    Used as an index-friendly SQL prefilter before exact haversine scoring.
    """
    lat_delta = radius_km / 111.32
    # Longitude degrees shrink with latitude; guard against the poles.
    cos_lat = max(math.cos(math.radians(lat)), 0.01)
    lon_delta = radius_km / (111.32 * cos_lat)
    return (
        max(-90.0, lat - lat_delta),
        min(90.0, lat + lat_delta),
        max(-180.0, lon - lon_delta),
        min(180.0, lon + lon_delta),
    )


def distance_between(
    a_lat: float | None, a_lon: float | None, b_lat: float | None, b_lon: float | None
) -> float | None:
    """Distance in km, or None when either point is unknown."""
    if a_lat is None or a_lon is None or b_lat is None or b_lon is None:
        return None
    return round(haversine_km(a_lat, a_lon, b_lat, b_lon), 2)


def location_fit_score(distance_km: float | None, radius_km: float) -> float:
    """Graded 0..1 proximity score.

    Full marks within a quarter of the acceptable radius, decaying linearly to
    zero at the radius edge. Unknown distance scores a neutral 0.5 rather than
    zero, so a record with missing coordinates is not silently buried.
    """
    if distance_km is None:
        return 0.5
    if radius_km <= 0:
        return 0.0
    comfortable = radius_km * 0.25
    if distance_km <= comfortable:
        return 1.0
    if distance_km >= radius_km:
        return 0.0
    return round(1.0 - (distance_km - comfortable) / (radius_km - comfortable), 4)
