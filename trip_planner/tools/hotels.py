"""Hotel search via SerpApi Google Hotels."""

from __future__ import annotations

from datetime import date

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
    raise NotImplementedError
