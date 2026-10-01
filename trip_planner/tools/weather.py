"""Weather forecast via OpenWeatherMap."""

from __future__ import annotations

from datetime import date


async def get_weather(lat: float, lng: float, start: date, end: date) -> list[dict]:
    """[{"date": "2026-05-01", "summary": "light rain", "high_c": 19, "low_c": 12,
    "precip_prob": 0.6}] for dates inside the forecast window; [] beyond it."""
    raise NotImplementedError
