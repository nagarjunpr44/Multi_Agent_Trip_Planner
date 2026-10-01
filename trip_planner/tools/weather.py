"""Weather forecast via OpenWeatherMap."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta

from trip_planner.config import get_settings
from trip_planner.tools import http
from trip_planner.tools.cache import cached


async def get_weather(lat: float, lng: float, start: date, end: date) -> list[dict]:
    """[{"date": "2026-05-01", "summary": "light rain", "high_c": 19, "low_c": 12,
    "precip_prob": 0.6}] for dates inside the forecast window; [] beyond it."""
    args = {"lat": round(lat, 3), "lng": round(lng, 3), "start": start, "end": end}

    async def fetch() -> list[dict]:
        key = http.require_key(get_settings().openweathermap_api_key, "OPENWEATHERMAP_API_KEY")
        data = await http.request(
            "OpenWeatherMap",
            "GET",
            "https://api.openweathermap.org/data/2.5/forecast",
            params={"lat": lat, "lon": lng, "units": "metric", "appid": key},
        )
        return _daily(data, start, end)

    return await cached("weather", args, fetch, ttl_hours=3)


def _daily(data: dict, start: date, end: date) -> list[dict]:
    """Group the 3-hourly steps by local date (city.timezone is the UTC offset in seconds)."""
    offset = timedelta(seconds=(data.get("city") or {}).get("timezone", 0))
    steps = defaultdict(list)
    for step in data.get("list", []):
        day = (datetime.fromtimestamp(step["dt"], UTC) + offset).date()
        if start <= day <= end:
            steps[day].append(step)
    days = []
    for day, ss in sorted(steps.items()):
        descriptions = Counter(s["weather"][0]["description"] for s in ss if s.get("weather"))
        days.append({
            "date": day.isoformat(),
            "summary": descriptions.most_common(1)[0][0] if descriptions else "",
            "high_c": round(max(s["main"]["temp_max"] for s in ss)),
            "low_c": round(min(s["main"]["temp_min"] for s in ss)),
            "precip_prob": round(max(s.get("pop", 0) for s in ss), 2),
        })
    return days
