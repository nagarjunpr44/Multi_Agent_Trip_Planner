from datetime import date, datetime

import httpx
import pytest

from trip_planner import store
from trip_planner.tests.test_tools_http import mock_http, set_key
from trip_planner.tools import ToolError
from trip_planner.tools.flights import search_flights


def _seg(dep, dep_t, arr, arr_t, airline):
    return {
        "departure_airport": {"name": dep, "id": dep, "time": dep_t},
        "arrival_airport": {"name": arr, "id": arr, "time": arr_t},
        "duration": 400,
        "airline": airline,
        "flight_number": "XX 1",
    }


PAYLOAD = {
    "search_metadata": {"google_flights_url": "https://www.google.com/travel/flights?x"},
    "best_flights": [
        {
            "flights": [
                _seg("JFK", "2026-05-01 18:00", "LHR", "2026-05-02 06:00", "British Airways"),
                _seg("LHR", "2026-05-02 08:00", "LIS", "2026-05-02 10:45", "TAP Air Portugal"),
            ],
            "total_duration": 705,
            "price": 912,
            "departure_token": "dep-1",
        }
    ],
    "other_flights": [
        {
            "flights": [_seg("JFK", "2026-05-01 19:30", "LIS", "2026-05-02 07:25", "TAP")],
            "total_duration": 415,
            "price": 640,
            "departure_token": "dep-2",
        },
        {"flights": [_seg("JFK", "2026-05-01 20:00", "LIS", "2026-05-02 08:00", "X")]},  # no price
    ],
}


async def test_search_flights_parses_and_sorts(monkeypatch):
    set_key(monkeypatch, "serpapi_api_key", "k")
    calls = mock_http(monkeypatch, lambda r: httpx.Response(200, json=PAYLOAD))
    flights = await search_flights("New York", "lis", date(2026, 5, 1), date(2026, 5, 8), adults=2)

    q = calls[0].url.params
    assert (q["engine"], q["departure_id"], q["arrival_id"]) == ("google_flights", "JFK", "LIS")
    assert (q["type"], q["return_date"], q["adults"]) == ("1", "2026-05-08", "2")
    assert q["travel_class"] == "1" and q["api_key"] == "k"
    assert [f.id for f in flights] == ["dep-2", "dep-1"]
    f = flights[1]
    assert f.airline == "British Airways, TAP Air Portugal"
    assert (f.origin, f.destination, f.stops, f.duration_min) == ("JFK", "LIS", 1, 705)
    assert f.depart_at == datetime(2026, 5, 1, 18, 0)
    assert f.arrive_at == datetime(2026, 5, 2, 10, 45)
    assert f.return_date == date(2026, 5, 8)
    assert f.price_usd == 912
    assert f.booking_url.startswith("https://www.google.com/travel")


async def test_search_flights_one_way_and_max_results(monkeypatch):
    set_key(monkeypatch, "serpapi_api_key", "k")
    calls = mock_http(monkeypatch, lambda r: httpx.Response(200, json=PAYLOAD))
    flights = await search_flights("JFK", "LIS", date(2026, 5, 1), cabin="business", max_results=1)
    assert calls[0].url.params["type"] == "2"
    assert calls[0].url.params["travel_class"] == "3"
    assert "return_date" not in calls[0].url.params
    assert len(flights) == 1 and flights[0].return_date is None


async def test_search_flights_errors(monkeypatch):
    set_key(monkeypatch, "serpapi_api_key", "")
    with pytest.raises(ToolError, match="SERPAPI_API_KEY is not configured"):
        await search_flights("JFK", "LIS", date(2026, 5, 1))
    with pytest.raises(ToolError, match="Unknown airport for 'Atlantis'"):
        await search_flights("Atlantis", "LIS", date(2026, 5, 1))
    set_key(monkeypatch, "serpapi_api_key", "k")
    mock_http(monkeypatch, lambda r: httpx.Response(401, json={"error": "Invalid API key."}))
    with pytest.raises(ToolError, match="401: Invalid API key"):
        await search_flights("JFK", "LIS", date(2026, 5, 1))


async def test_search_flights_cached(monkeypatch, tmp_path):
    set_key(monkeypatch, "serpapi_api_key", "k")
    calls = mock_http(monkeypatch, lambda r: httpx.Response(200, json=PAYLOAD))
    await store.init_db(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        first = await search_flights("JFK", "LIS", date(2026, 5, 1))
        second = await search_flights("JFK", "LIS", date(2026, 5, 1))
    finally:
        await store.close_db()
    assert len(calls) == 1
    assert first == second
