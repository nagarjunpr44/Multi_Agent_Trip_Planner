"""Hotel search via SerpApi Google Hotels."""

from __future__ import annotations

from datetime import date

from trip_planner.tools import ToolError, http
from trip_planner.tools.cache import cached
from trip_planner.trip.models import HotelOption


async def search_hotels(
    city: str,
    check_in: date,
    check_out: date,
    adults: int = 1,
    max_price_per_night: float | None = None,
    min_stars: int | None = None,
    near: str | None = None,
    max_results: int = 6,
) -> list[HotelOption]:
    """`near` biases the search to a neighborhood, e.g. "Alfama"."""
    nights = (check_out - check_in).days
    if nights < 1:
        raise ToolError("check_out must be after check_in")
    params: dict = {
        "engine": "google_hotels",
        "q": f"{near}, {city}" if near else city,
        "check_in_date": check_in.isoformat(),
        "check_out_date": check_out.isoformat(),
        "adults": adults,
        "currency": "USD",
    }
    if min_stars and min_stars > 1:  # Google Hotels classes start at 2
        params["hotel_class"] = ",".join(str(s) for s in range(min(min_stars, 5), 6))
    if max_price_per_night:
        params["max_price"] = int(max_price_per_night)

    async def fetch() -> list[dict]:
        data = await http.serpapi(params)
        options = [_option(p, check_in, check_out, nights) for p in data.get("properties", [])]
        options = sorted((o for o in options if o), key=lambda o: o.price_per_night_usd)
        return [o.model_dump(mode="json") for o in options]

    rows = await cached("hotels", params, fetch, ttl_hours=6)
    return [HotelOption.model_validate(r) for r in rows[:max_results]]


def _option(prop: dict, check_in: date, check_out: date, nights: int) -> HotelOption | None:
    ppn = (prop.get("rate_per_night") or {}).get("extracted_lowest")
    if not ppn:
        return None
    gps = prop.get("gps_coordinates") or {}
    total = (prop.get("total_rate") or {}).get("extracted_lowest") or ppn * nights
    return HotelOption(
        id=prop.get("property_token") or prop.get("name", ""),
        name=prop.get("name", ""),
        lat=gps.get("latitude"),
        lng=gps.get("longitude"),
        check_in=check_in,
        check_out=check_out,
        price_per_night_usd=float(ppn),
        total_usd=float(total),
        rating=prop.get("overall_rating"),
        stars=prop.get("extracted_hotel_class"),
        booking_url=prop.get("link", ""),
        photo_url=next(iter(prop.get("images") or []), {}).get("thumbnail", ""),
    )
