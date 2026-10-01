"""Straight-line distances. Good enough to spot a scattered day."""

from __future__ import annotations

from itertools import combinations
from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lat, lng) points."""
    lat1, lng1, lat2, lng2 = map(radians, (*a, *b))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(h))


def max_spread_km(points: list[tuple[float, float]]) -> float:
    """Largest pairwise distance; 0 for fewer than two points."""
    # ponytail: O(n^2), fine for a day's handful of stops
    return max((haversine_km(a, b) for a, b in combinations(points, 2)), default=0.0)
