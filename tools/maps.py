from __future__ import annotations

import json

import httpx
from langchain_core.tools import tool
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import get_settings

MAPS_BASE = "https://maps.googleapis.com/maps/api/distancematrix/json"


def _maps_key_configured(api_key: str) -> bool:
    if not api_key:
        return False
    placeholders = ("...", "your_", "xxx", "placeholder")
    return not any(p in api_key.lower() for p in placeholders)


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _fetch_google_distance(origin: str, destination: str, mode: str, api_key: str) -> dict:
    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.get(
            MAPS_BASE,
            params={
                "origins": origin,
                "destinations": destination,
                "mode": mode,
                "key": api_key,
                "units": "metric",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    api_status = data.get("status")
    if api_status and api_status != "OK":
        raise ValueError(f"Distance Matrix API status: {api_status}")

    rows = data.get("rows") or []
    if not rows:
        raise ValueError("Distance Matrix API returned no rows")

    elements = rows[0].get("elements") or []
    if not elements:
        raise ValueError("Distance Matrix API returned no elements")

    element = elements[0]
    if element.get("status") != "OK":
        raise ValueError(f"Distance API returned: {element.get('status')}")

    distance_m = element["distance"]["value"]
    duration_s = element["duration"]["value"]
    return {
        "origin": origin,
        "destination": destination,
        "mode": mode,
        "distance_km": round(distance_m / 1000, 2),
        "duration_minutes": round(duration_s / 60),
    }


@tool
async def get_travel_distance_tool(
    origin: str,
    destination: str,
    mode: str = "transit",
) -> str:
    """Get travel distance and duration between two locations.

    Args:
        origin: Starting location (address, place name, or lat,lng)
        destination: Destination location (address, place name, or lat,lng)
        mode: Transport mode: walking | transit | driving | bicycling

    Returns:
        JSON with distance_km and duration_minutes
    """
    s = get_settings()
    api_key = s.apis.google_maps_api_key
    if not _maps_key_configured(api_key):
        return json.dumps(
            {"error": "GOOGLE_MAPS_API_KEY is not configured. Cannot compute distance."}
        )

    try:
        result = await _fetch_google_distance(origin, destination, mode, api_key)
    except Exception as exc:
        return json.dumps({"error": str(exc), "origin": origin, "destination": destination})

    return json.dumps(result)
