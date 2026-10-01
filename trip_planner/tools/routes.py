"""Travel times via Google Routes API, with a haversine fallback."""

from __future__ import annotations

import math

from trip_planner.config import get_settings
from trip_planner.tools import ToolError, http
from trip_planner.tools.cache import cached
from trip_planner.trip.geo import haversine_km

_MODES = {"walk": "WALK", "transit": "TRANSIT", "drive": "DRIVE"}


async def travel_minutes(
    a: tuple[float, float], b: tuple[float, float], mode: str = "transit"
) -> int:
    """mode: walk | transit | drive. Never raises for missing key / API failure:
    falls back to a straight-line estimate instead."""
    if mode not in _MODES:
        raise ToolError(f"Unknown travel mode '{mode}' — use walk, transit or drive")
    args = {"a": [round(x, 5) for x in a], "b": [round(x, 5) for x in b], "mode": mode}
    try:
        # Only API answers are cached, so adding a key later takes effect at once.
        return await cached("routes", args, lambda: _api_minutes(a, b, mode), ttl_hours=24 * 30)
    except ToolError:
        return estimate_minutes(a, b, mode)


async def _api_minutes(a: tuple[float, float], b: tuple[float, float], mode: str) -> int:
    key = http.require_key(get_settings().google_maps_api_key, "GOOGLE_MAPS_API_KEY")
    data = await http.request(
        "Google Routes",
        "POST",
        "https://routes.googleapis.com/directions/v2:computeRoutes",
        json={
            "origin": {"location": {"latLng": {"latitude": a[0], "longitude": a[1]}}},
            "destination": {"location": {"latLng": {"latitude": b[0], "longitude": b[1]}}},
            "travelMode": _MODES[mode],
        },
        headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": "routes.duration"},
    )
    routes = data.get("routes") or []
    if not routes or "duration" not in routes[0]:
        raise ToolError("Google Routes returned no route")
    seconds = int(routes[0]["duration"].rstrip("s"))
    return max(1, math.ceil(seconds / 60))


def estimate_minutes(a: tuple[float, float], b: tuple[float, float], mode: str) -> int:
    """Straight-line guess: walking at 4.5 km/h on a 1.3x detour; transit/drive add a fixed
    wait/parking overhead to a crow-flies average speed."""
    km = haversine_km(a, b)
    minutes = {
        "walk": km * 1.3 / 4.5 * 60,
        "transit": 8 + km / 18 * 60,
        "drive": 5 + km / 25 * 60,
    }[mode]
    return max(1, round(minutes))

