"""Flight search via SerpApi Google Flights."""

from __future__ import annotations

from datetime import date, datetime

from trip_planner.tools import ToolError, http
from trip_planner.tools.cache import cached
from trip_planner.trip.models import FlightOption

# ponytail: small city→airport map; the planner can always pass an IATA code instead.
_CITY_TO_AIRPORT = {
    "amsterdam": "AMS",
    "athens": "ATH",
    "bangkok": "BKK",
    "barcelona": "BCN",
    "berlin": "BER",
    "boston": "BOS",
    "chicago": "ORD",
    "delhi": "DEL",
    "dubai": "DXB",
    "dublin": "DUB",
    "frankfurt": "FRA",
    "hong kong": "HKG",
    "istanbul": "IST",
    "kyoto": "KIX",
    "las vegas": "LAS",
    "lisbon": "LIS",
    "london": "LHR",
    "los angeles": "LAX",
    "madrid": "MAD",
    "miami": "MIA",
    "milan": "MXP",
    "new york": "JFK",
    "osaka": "KIX",
    "paris": "CDG",
    "rome": "FCO",
    "san francisco": "SFO",
    "seattle": "SEA",
    "seoul": "ICN",
    "singapore": "SIN",
    "sydney": "SYD",
    "tokyo": "HND",
    "toronto": "YYZ",
    "vancouver": "YVR",
    "vienna": "VIE",
    "zurich": "ZRH",
}

_CABINS = {"economy": 1, "premium_economy": 2, "business": 3, "first": 4}


def airport_code(value: str) -> str:
    cleaned = " ".join(value.strip().lower().replace(",", " ").split())
    if len(cleaned) == 3 and cleaned.isalpha():
        return cleaned.upper()
    if cleaned in _CITY_TO_AIRPORT:
        return _CITY_TO_AIRPORT[cleaned]
    raise ToolError(f"Unknown airport for '{value}' — pass a 3-letter IATA code")


async def search_flights(
    origin: str,
    destination: str,
    depart: date,
    return_date: date | None = None,
    adults: int = 1,
    cabin: str = "economy",
    max_results: int = 6,
) -> list[FlightOption]:
    """origin/destination: city name or IATA code. Cheapest first.
    price_usd is the total for all adults (round trip when return_date is set)."""
    params = {
        "engine": "google_flights",
        "departure_id": airport_code(origin),
        "arrival_id": airport_code(destination),
        "outbound_date": depart.isoformat(),
        "type": 1 if return_date else 2,
        "adults": adults,
        "travel_class": _CABINS.get(cabin.lower().replace(" ", "_").replace("-", "_"), 1),
        "currency": "USD",
    }
    if return_date:
        params["return_date"] = return_date.isoformat()

    async def fetch() -> list[dict]:
        data = await http.serpapi(params)
        url = data.get("search_metadata", {}).get("google_flights_url", "")
        raw = data.get("best_flights", []) + data.get("other_flights", [])
        options = [_option(f, i, url, params, return_date) for i, f in enumerate(raw)]
        options = sorted((o for o in options if o), key=lambda o: o.price_usd)
        return [o.model_dump(mode="json") for o in options]

    rows = await cached("flights", params, fetch, ttl_hours=6)
    return [FlightOption.model_validate(r) for r in rows[:max_results]]


def _option(
    flight: dict, i: int, url: str, params: dict, return_date: date | None
) -> FlightOption | None:
    segments = flight.get("flights") or []
    price = flight.get("price")
    if not segments or not isinstance(price, int | float):
        return None
    first, last = segments[0], segments[-1]
    airlines = dict.fromkeys(s.get("airline", "") for s in segments if s.get("airline"))
    return FlightOption(
        id=flight.get("booking_token") or flight.get("departure_token") or f"f{i}",
        airline=", ".join(airlines) or "Unknown",
        origin=first.get("departure_airport", {}).get("id") or params["departure_id"],
        destination=last.get("arrival_airport", {}).get("id") or params["arrival_id"],
        depart_at=_time(first["departure_airport"]["time"]),
        arrive_at=_time(last["arrival_airport"]["time"]),
        return_date=return_date,
        stops=len(segments) - 1,
        duration_min=flight.get("total_duration", 0),
        price_usd=float(price),
        booking_url=url,
    )


def _time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M")
