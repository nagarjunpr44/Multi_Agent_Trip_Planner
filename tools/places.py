from __future__ import annotations

import json

import httpx
from langchain_core.tools import tool
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import get_settings
from schemas.itinerary import Experience

# Foursquare Places API v3
FSQ_BASE = "https://api.foursquare.com/v3/places/search"

# Foursquare category IDs mapped to our internal categories
# Full list: https://docs.foursquare.com/data-products/docs/categories
_FSQ_CATEGORIES: dict[str, str] = {
    "restaurant": "13065",   # Restaurant (parent: 13000 Dining & Drinking)
    "attraction": "16032",   # Tourist Attraction (parent: 16000 Landmarks & Outdoors)
    "hidden_gem": "16026",   # Scenic Lookout + Landmarks catch-all
    "activity": "18000",     # Sports & Recreation (18000)
}

# Fields to request — keeps response lean
_FSQ_FIELDS = "fsq_id,name,categories,location,rating,price,stats,geocodes,description,tel,website"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=20),
    reraise=True,
)
async def _fetch_foursquare_places(city: str, category: str, keyword: str) -> list[dict]:
    s = get_settings()
    api_key = s.apis.foursquare_api_key

    params: dict = {
        "near": city,
        "limit": 10,
        "fields": _FSQ_FIELDS,
    }
    if keyword:
        params["query"] = keyword
    fsq_cat = _FSQ_CATEGORIES.get(category)
    if fsq_cat:
        params["categories"] = fsq_cat

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            FSQ_BASE,
            params=params,
            headers={
                "Authorization": api_key,
                "Accept": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    results = []
    for place in data.get("results", [])[:8]:
        loc = place.get("location", {})
        geocodes = place.get("geocodes", {}).get("main", {})
        # Foursquare rating is 0–10; normalise to 0–5
        raw_rating = place.get("rating")
        rating = round(raw_rating / 2, 1) if raw_rating is not None else None
        # Foursquare price is 1–4 (matches Google scale directly)
        price = place.get("price")
        cats = place.get("categories", [])
        cuisine = cats[0]["name"] if cats and category == "restaurant" else None

        exp = Experience(
            name=place.get("name", ""),
            category=category,
            address=loc.get("formatted_address") or loc.get("address", ""),
            city=loc.get("locality") or city,
            rating=rating,
            num_reviews=place.get("stats", {}).get("total_ratings"),
            price_level=price,
            description=place.get("description") or place.get("name", ""),
            cuisine_type=cuisine,
            foursquare_id=place.get("fsq_id"),
            latitude=geocodes.get("latitude"),
            longitude=geocodes.get("longitude"),
        )
        results.append(exp.model_dump())
    return results


@tool
async def search_places_tool(
    city: str,
    category: str,
    keyword: str = "",
) -> str:
    """Search for places (restaurants, attractions, hidden gems, activities) in a city.

    Args:
        city: City name (e.g. "Tokyo", "Rome", "Bangkok")
        category: One of: restaurant | attraction | hidden_gem | activity
        keyword: Optional keyword to refine search (e.g. "sushi", "temple", "cooking class")

    Returns:
        JSON list of Experience objects
    """
    if not s.apis.foursquare_api_key:
        raise ValueError("FOURSQUARE_API_KEY is not configured.")
        
    results = await _fetch_foursquare_places(city, category, keyword or category)

    return json.dumps(results)
