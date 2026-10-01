"""Place search + details via Google Places API (New)."""

from __future__ import annotations

from trip_planner.trip.models import Place


async def search_places(query: str, near: str, max_results: int = 8) -> list[Place]:
    """Text search, e.g. ("ramen", "Shinjuku, Tokyo"). Includes hours when returned."""
    raise NotImplementedError


async def get_place(place_id: str) -> Place:
    """Full details for one place, including opening hours."""
    raise NotImplementedError
