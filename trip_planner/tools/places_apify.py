"""Place search + details via Apify's Google Maps scraper (compass/crawler-google-places).

Each call starts a scraper run and waits for its results, so it takes seconds to tens
of seconds; results are cached for a week. Opening hours need the detail-page scrape,
so it is always on: without hours, check_trip can't catch closed venues.
"""

from __future__ import annotations

import asyncio
import re
from datetime import time

from trip_planner.config import get_settings
from trip_planner.tools import ToolError, http
from trip_planner.tools.cache import cached
from trip_planner.trip.models import OpenPeriod, Place

RUN_URL = (
    "https://api.apify.com/v2/acts/compass~crawler-google-places/run-sync-get-dataset-items"
)
RUN_TIMEOUT_S = 150  # Apify stops waiting at this point; the run itself is billed until then
_TTL_HOURS = 24 * 7
# ponytail: per-process cap sized for a 16 GB / 5-job Apify plan; raise it on bigger plans.
_slots = asyncio.Semaphore(4)
_BASE_INPUT = {
    "language": "en",
    "scrapePlaceDetailPage": True,  # needed for openingHours
    "skipClosedPlaces": True,
    "maxReviews": 0,
    "maxImages": 0,
    "maxQuestions": 0,
    "scrapeContacts": False,
}
_WEEKDAYS = {d: i for i, d in enumerate(
    ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
)}


async def search_places(query: str, near: str, max_results: int = 8) -> list[Place]:
    return await search_many([query], near, max_results)


async def search_many(queries: list[str], near: str, max_results: int = 6) -> list[Place]:
    """One scraper run per query, run concurrently; deduplicated, in query order.

    A single run with several queries works through them roughly one after another
    (measured: 60-150s for 4-6 queries), while separate runs really run in parallel.
    """
    results = await asyncio.gather(*(_search_one(q, near, max_results) for q in queries))
    unique = {p.place_id: p for found in results for p in found}
    return list(unique.values())


async def _search_one(query: str, near: str, max_results: int) -> list[Place]:
    body = {
        **_BASE_INPUT,
        "searchStringsArray": [query],
        "locationQuery": near,
        "maxCrawledPlacesPerSearch": max_results,
    }
    rows = await cached("places.apify.search", body, lambda: _run(body), ttl_hours=_TTL_HOURS)
    return [Place.model_validate(r) for r in rows]


async def get_place(place_id: str) -> Place:
    body = {**_BASE_INPUT, "placeIds": [place_id]}
    rows = await cached("places.apify.get", body, lambda: _run(body), ttl_hours=_TTL_HOURS)
    if not rows:
        raise ToolError(f"No place found for place_id {place_id}")
    return Place.model_validate(rows[0])


async def _run(body: dict) -> list[dict]:
    token = http.require_key(get_settings().apify_api_token, "APIFY_API_TOKEN")
    async with _slots:
        items = await http.request(
            "Apify",
            "POST",
            RUN_URL,
            params={"timeout": RUN_TIMEOUT_S},
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=RUN_TIMEOUT_S + 30,
        )
    return [
        _place(item).model_dump(mode="json")
        for item in items
        if item.get("placeId") and not item.get("permanentlyClosed")
    ]


def _place(p: dict) -> Place:
    loc = p.get("location") or {}
    return Place(
        place_id=p["placeId"],
        name=p.get("title", ""),
        address=p.get("address") or "",
        lat=loc.get("lat"),
        lng=loc.get("lng"),
        rating=p.get("totalScore"),
        user_ratings=p.get("reviewsCount"),
        price_level=_price_level(p.get("price")),
        types=p.get("categories") or ([p["categoryName"]] if p.get("categoryName") else []),
        hours=parse_hours(p.get("openingHours")),
        maps_url=p.get("url") or "",
        website=p.get("website") or "",
    )


def _price_level(price: str | None) -> int | None:
    """"$$" → 2. Ranges like "$10–20" don't map to a level, so they're unknown."""
    if price and set(price) == {"$"}:
        return min(len(price), 4)
    return None


# ── Opening hours: "11 AM to 9:30 PM", "Closed", "Open 24 hours", "11 AM to 3 PM, 5 to 10 PM"

_TIME = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$")


def parse_hours(rows: list[dict] | None) -> list[OpenPeriod] | None:
    """None (unknown) unless every listed day parses: a wrong guess would make
    check_trip report a venue as closed when it's open."""
    if not rows:
        return None
    periods: list[OpenPeriod] = []
    for row in rows:
        weekday = _WEEKDAYS.get(str(row.get("day", "")).strip().lower())
        text = _normalize(str(row.get("hours", "")))
        if weekday is None or not text:
            return None
        if text == "closed":
            continue
        if text in ("open 24 hours", "24 hours"):
            periods.append(OpenPeriod(weekday=weekday, open=time(0), close=time(0)))
            continue
        for part in text.split(","):
            span = _span(part.strip())
            if span is None:
                return None
            periods.append(OpenPeriod(weekday=weekday, open=span[0], close=span[1]))
    return periods


def _normalize(text: str) -> str:
    for ch in (" ", " ", "\xa0"):
        text = text.replace(ch, " ")
    text = re.sub(r"\s*[–—-]\s*", " to ", text.lower())
    return re.sub(r"\s+", " ", text).replace("a.m.", "am").replace("p.m.", "pm").strip()


def _span(part: str) -> tuple[time, time] | None:
    if " to " not in part:
        return None
    a, b = (s.strip() for s in part.split(" to ", 1))
    ma, mb = _TIME.match(a), _TIME.match(b)
    if not ma or not mb:
        return None
    end = _to_time(mb, mb.group(3))
    if end is None:
        return None
    # "5 to 10 PM": the start inherits the end's AM/PM, unless that puts it after
    # the end on the same day ("11 to 2 PM" means 11 AM).
    start = _to_time(ma, ma.group(3) or mb.group(3))
    if start is None:
        return None
    if not ma.group(3) and mb.group(3) == "pm" and start > end:
        start = _to_time(ma, "am")
    return start, end


def _to_time(m: re.Match, meridiem: str | None) -> time | None:
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    if meridiem is None:  # 24h clock, e.g. "09:00 to 17:00"
        return time(hour, minute) if hour < 24 and minute < 60 else None
    if not 1 <= hour <= 12 or minute >= 60:
        return None
    hour = hour % 12 + (12 if meridiem == "pm" else 0)
    return time(hour, minute)
