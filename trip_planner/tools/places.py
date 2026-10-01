"""Place search + details via Google Places API (New)."""

from __future__ import annotations

from datetime import time
from urllib.parse import quote

from trip_planner.config import get_settings
from trip_planner.tools import http
from trip_planner.tools.cache import cached
from trip_planner.trip.models import OpenPeriod, Place

_FIELDS = [
    "id",
    "displayName",
    "formattedAddress",
    "location",
    "rating",
    "userRatingCount",
    "priceLevel",
    "types",
    "regularOpeningHours",
    "googleMapsUri",
    "websiteUri",
]
_PRICE_LEVELS = {
    "PRICE_LEVEL_FREE": 0,
    "PRICE_LEVEL_INEXPENSIVE": 1,
    "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}
_TTL_HOURS = 24 * 7


def _headers(field_mask: str) -> dict:
    key = http.require_key(get_settings().places_key, "GOOGLE_PLACES_API_KEY")
    return {"X-Goog-Api-Key": key, "X-Goog-FieldMask": field_mask}


async def search_places(query: str, near: str, max_results: int = 8) -> list[Place]:
    """Text search, e.g. ("ramen", "Shinjuku, Tokyo"). Includes hours when returned."""
    body = {"textQuery": f"{query} in {near}", "pageSize": min(max_results, 20)}

    async def fetch() -> list[dict]:
        data = await http.request(
            "Google Places",
            "POST",
            "https://places.googleapis.com/v1/places:searchText",
            json=body,
            headers=_headers(",".join(f"places.{f}" for f in _FIELDS)),
        )
        return [_place(p).model_dump(mode="json") for p in data.get("places", [])]

    rows = await cached("places.search", body, fetch, ttl_hours=_TTL_HOURS)
    return [Place.model_validate(r) for r in rows]


async def get_place(place_id: str) -> Place:
    """Full details for one place, including opening hours."""

    async def fetch() -> dict:
        data = await http.request(
            "Google Places",
            "GET",
            f"https://places.googleapis.com/v1/places/{quote(place_id, safe='')}",
            headers=_headers(",".join(_FIELDS)),
        )
        return _place(data).model_dump(mode="json")

    row = await cached("places.get", {"place_id": place_id}, fetch, ttl_hours=_TTL_HOURS)
    return Place.model_validate(row)


def _place(p: dict) -> Place:
    loc = p.get("location") or {}
    hours = p.get("regularOpeningHours")
    return Place(
        place_id=p["id"],
        name=(p.get("displayName") or {}).get("text", ""),
        address=p.get("formattedAddress", ""),
        lat=loc.get("latitude"),
        lng=loc.get("longitude"),
        rating=p.get("rating"),
        user_ratings=p.get("userRatingCount"),
        price_level=_PRICE_LEVELS.get(p.get("priceLevel", "")),
        types=p.get("types", []),
        hours=None if hours is None else _hours(hours.get("periods", [])),
        maps_url=p.get("googleMapsUri", ""),
        website=p.get("websiteUri", ""),
    )


def _hours(periods: list[dict]) -> list[OpenPeriod]:
    """Google days are Sunday=0; ours are Monday=0. close <= open means past midnight."""
    out = []
    for period in periods:
        o, c = period.get("open") or {}, period.get("close")
        opens = time(o.get("hour", 0), o.get("minute", 0))
        if c is None:
            if o.get("day", 0) == 0 and opens == time(0):  # Google's marker for open 24/7
                return [OpenPeriod(weekday=d, open=time(0), close=time(0)) for d in range(7)]
            continue
        closes = time(c.get("hour", 0) % 24, c.get("minute", 0))
        out.append(OpenPeriod(weekday=(o.get("day", 0) + 6) % 7, open=opens, close=closes))
    return out
