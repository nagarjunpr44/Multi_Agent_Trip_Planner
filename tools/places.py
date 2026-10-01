from __future__ import annotations

import json
import os

import httpx
from langchain_core.tools import tool
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import get_settings
from schemas.itinerary import Experience

# Foursquare Places API v3
FSQ_BASE = "https://api.foursquare.com/v3/places/search"

_FSQ_CATEGORIES: dict[str, str] = {
    "restaurant": "13065",
    "attraction": "16032",
    "hidden_gem": "16026",
    "activity": "18000",
}

_FSQ_FIELDS = "fsq_id,name,categories,location,rating,price,stats,geocodes,description,tel,website"

_CATEGORY_QUERY: dict[str, str] = {
    "restaurant": "best restaurants",
    "attraction": "top attractions",
    "hidden_gem": "hidden gems off the beaten path",
    "activity": "things to do activities",
}


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
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            return []
        data = resp.json()

    results = []
    for place in data.get("results", [])[:8]:
        loc = place.get("location", {})
        geocodes = place.get("geocodes", {}).get("main", {})
        raw_rating = place.get("rating")
        rating = round(raw_rating / 2, 1) if raw_rating is not None else None
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


async def _fetch_places_via_tavily(city: str, category: str, keyword: str) -> list[dict]:
    """Web search fallback when Foursquare is not configured."""
    s = get_settings()
    if not s.apis.tavily_api_key:
        return []

    os.environ["TAVILY_API_KEY"] = s.apis.tavily_api_key
    from langchain_tavily import TavilySearch

    topic = keyword or _CATEGORY_QUERY.get(category, category)
    query = f"{city} {topic}"
    search_tool = TavilySearch(max_results=6, search_depth="basic", topic="general")
    raw = search_tool.invoke({"query": query})

    items: list[dict] = []
    if isinstance(raw, dict):
        items = raw.get("results", [])
    elif isinstance(raw, list):
        items = raw

    results: list[dict] = []
    for item in items[:6]:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        content = (item.get("content") or item.get("snippet") or "")[:400]
        exp = Experience(
            name=title[:120],
            category=category,
            address="",
            city=city,
            description=content or title,
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
    s = get_settings()
    search_term = keyword or category

    fsq_key = s.apis.foursquare_api_key
    if fsq_key and "..." not in fsq_key:
        results = await _fetch_foursquare_places(city, category, search_term)
        if results:
            return json.dumps(results)

    results = await _fetch_places_via_tavily(city, category, search_term)
    if results:
        return json.dumps(results)

    if not s.apis.foursquare_api_key and not s.apis.tavily_api_key:
        return json.dumps({
            "error": (
                "Configure FOURSQUARE_API_KEY or TAVILY_API_KEY to search places."
            )
        })

    return json.dumps([])
