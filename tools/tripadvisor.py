from __future__ import annotations

import json

import httpx
from langchain_core.tools import tool

from config.settings import get_settings

_BASE_URL = "https://api.content.tripadvisor.com/api/v1"
_TIMEOUT = 10.0


def _mock_tripadvisor(destination: str, category: str) -> dict:
    return {
        "destination": destination,
        "category": category,
        "location_id": "mock-id",
        "name": destination,
        "rating": 4.5,
        "review_count": 1200,
        "description": f"{destination} is a vibrant destination known for its rich culture and attractions.",
        "top_attractions": [
            {"name": f"{destination} Old Town", "rating": 4.7, "review_count": 850},
            {"name": f"{destination} Museum", "rating": 4.4, "review_count": 620},
            {"name": f"{destination} Central Park", "rating": 4.3, "review_count": 490},
        ],
        "source": "mock",
        "is_mock": True,
    }


async def _fetch_tripadvisor(destination: str, category: str, api_key: str) -> dict:
    """
    Two-step TripAdvisor Content API call:
      1. Location search to get location_id
      2. Location details + nearby attractions
    """
    headers = {"accept": "application/json", "referer": "agentictripplanner"}

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        # Step 1 — find the location
        search_resp = await client.get(
            f"{_BASE_URL}/location/search",
            params={
                "key": api_key,
                "searchQuery": destination,
                "category": category,
                "language": "en",
            },
            headers=headers,
        )
        search_resp.raise_for_status()
        locations = search_resp.json().get("data", [])
        if not locations:
            return {"destination": destination, "category": category, "error": "no results", "is_mock": False}

        loc = locations[0]
        location_id = loc["location_id"]

        # Step 2 — get full details for the top result
        detail_resp = await client.get(
            f"{_BASE_URL}/location/{location_id}/details",
            params={"key": api_key, "language": "en", "currency": "USD"},
            headers=headers,
        )
        detail_resp.raise_for_status()
        details = detail_resp.json()

        # Step 3 — nearby attractions
        nearby_resp = await client.get(
            f"{_BASE_URL}/location/{location_id}/nearby_search",
            params={
                "key": api_key,
                "category": "attractions",
                "language": "en",
            },
            headers=headers,
        )
        nearby_data = nearby_resp.json().get("data", []) if nearby_resp.is_success else []
        top_attractions = [
            {"name": a.get("name", ""), "location_id": a.get("location_id", "")}
            for a in nearby_data[:5]
        ]

        return {
            "destination": destination,
            "category": category,
            "location_id": location_id,
            "name": details.get("name", destination),
            "description": details.get("description", ""),
            "rating": details.get("rating"),
            "review_count": details.get("num_reviews"),
            "price_level": details.get("price_level"),
            "web_url": details.get("web_url", ""),
            "address": details.get("address_obj", {}),
            "timezone": details.get("timezone"),
            "awards": [a.get("display_name", "") for a in details.get("awards", [])[:3]],
            "top_attractions": top_attractions,
            "source": "tripadvisor",
            "is_mock": False,
        }


@tool
async def search_tripadvisor_tool(destination: str, category: str = "geos") -> str:
    """Search TripAdvisor for destination details, ratings, and top attractions.

    Args:
        destination: City or place name (e.g. "Tokyo", "Paris", "Kyoto")
        category: "geos" for destination overview | "attractions" | "hotels" | "restaurants"

    Returns:
        JSON with location details, rating, review count, and top nearby attractions
    """
    s = get_settings()
    if s.app.mock_fallback or not s.apis.tripadvisor_api_key:
        return json.dumps(_mock_tripadvisor(destination, category))

    try:
        result = await _fetch_tripadvisor(destination, category, s.apis.tripadvisor_api_key)
        return json.dumps(result)
    except Exception as exc:
        fallback = _mock_tripadvisor(destination, category)
        fallback["error"] = str(exc)
        return json.dumps(fallback)
