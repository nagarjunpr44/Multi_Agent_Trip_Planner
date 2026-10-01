from datetime import UTC, date, datetime

import httpx
import pytest

from trip_planner import store
from trip_planner.tests.test_tools_http import mock_http, set_key
from trip_planner.tools import ToolError
from trip_planner.tools.weather import get_weather


def _step(utc: str, temp_min, temp_max, desc, pop):
    dt = datetime.fromisoformat(utc).replace(tzinfo=UTC)
    return {
        "dt": int(dt.timestamp()),
        "main": {"temp": temp_max, "temp_min": temp_min, "temp_max": temp_max, "humidity": 70},
        "weather": [{"id": 500, "main": "Rain", "description": desc, "icon": "10d"}],
        "pop": pop,
        "dt_txt": utc.replace("T", " "),
    }


# Tokyo is UTC+9: 2026-04-30 18:00 UTC is already May 1 locally.
PAYLOAD = {
    "cod": "200",
    "list": [
        _step("2026-04-30T12:00:00", 14.0, 15.0, "clear sky", 0),  # Apr 30 21:00 local
        _step("2026-04-30T18:00:00", 12.4, 13.0, "light rain", 0.4),  # May 1 03:00
        _step("2026-05-01T03:00:00", 16.0, 19.6, "light rain", 0.62),  # May 1 12:00
        _step("2026-05-01T09:00:00", 15.0, 17.0, "overcast clouds", 0.1),  # May 1 18:00
        _step("2026-05-01T21:00:00", 11.0, 12.0, "few clouds", 0),  # May 2 06:00
    ],
    "city": {"name": "Tokyo", "timezone": 32400},
}


async def test_get_weather_aggregates_by_local_date(monkeypatch):
    set_key(monkeypatch, "openweathermap_api_key", "wk")
    calls = mock_http(monkeypatch, lambda r: httpx.Response(200, json=PAYLOAD))
    days = await get_weather(35.68, 139.69, date(2026, 5, 1), date(2026, 5, 4))

    q = calls[0].url.params
    assert (q["lat"], q["lon"], q["units"], q["appid"]) == ("35.68", "139.69", "metric", "wk")
    assert days == [
        {"date": "2026-05-01", "summary": "light rain", "high_c": 20, "low_c": 12,
         "precip_prob": 0.62},
        {"date": "2026-05-02", "summary": "few clouds", "high_c": 12, "low_c": 11,
         "precip_prob": 0},
    ]


async def test_get_weather_beyond_forecast_and_cache(monkeypatch, tmp_path):
    set_key(monkeypatch, "openweathermap_api_key", "wk")
    calls = mock_http(monkeypatch, lambda r: httpx.Response(200, json=PAYLOAD))
    await store.init_db(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        assert await get_weather(35.68, 139.69, date(2026, 6, 1), date(2026, 6, 3)) == []
        assert await get_weather(35.68, 139.69, date(2026, 6, 1), date(2026, 6, 3)) == []
    finally:
        await store.close_db()
    assert len(calls) == 1


async def test_get_weather_errors(monkeypatch):
    set_key(monkeypatch, "openweathermap_api_key", "")
    with pytest.raises(ToolError, match="OPENWEATHERMAP_API_KEY is not configured"):
        await get_weather(0, 0, date(2026, 5, 1), date(2026, 5, 2))
    set_key(monkeypatch, "openweathermap_api_key", "bad")
    mock_http(monkeypatch, lambda r: httpx.Response(401, json={
        "cod": 401, "message": "Invalid API key. Please see https://openweathermap.org/faq"
    }))
    with pytest.raises(ToolError, match="401: Invalid API key"):
        await get_weather(0, 0, date(2026, 5, 1), date(2026, 5, 2))


async def test_geocode(monkeypatch):
    from trip_planner.tools.weather import geocode

    set_key(monkeypatch, "openweathermap_api_key", "k")
    calls = mock_http(monkeypatch, lambda r: httpx.Response(
        200, json=[{"name": "Lisbon", "lat": 38.7077, "lon": -9.1365, "country": "PT"}]
    ))
    assert await geocode("Lisbon") == (38.7077, -9.1365)
    assert calls[0].url.path == "/geo/1.0/direct" and calls[0].url.params["q"] == "Lisbon"
    mock_http(monkeypatch, lambda r: httpx.Response(200, json=[]))
    with pytest.raises(ToolError, match="Could not locate Atlantis"):
        await geocode("Atlantis")
