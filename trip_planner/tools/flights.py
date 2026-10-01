"""Flight search via SerpApi Google Flights."""

from __future__ import annotations

from datetime import date

from trip_planner.trip.models import FlightOption


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
    raise NotImplementedError
