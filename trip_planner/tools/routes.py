"""Travel times via Google Routes API, with a haversine fallback."""

from __future__ import annotations


async def travel_minutes(
    a: tuple[float, float], b: tuple[float, float], mode: str = "transit"
) -> int:
    """mode: walk | transit | drive. Never raises for missing key / API failure:
    falls back to a straight-line estimate instead."""
    raise NotImplementedError
