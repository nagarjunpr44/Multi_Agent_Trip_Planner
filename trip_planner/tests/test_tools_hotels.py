from datetime import date

import httpx
import pytest

from trip_planner import store
from trip_planner.tests.test_tools_http import mock_http, set_key
from trip_planner.tools import ToolError
from trip_planner.tools.hotels import search_hotels

PAYLOAD = {
    "search_metadata": {"status": "Success"},
    "properties": [
        {
            "type": "hotel",
            "name": "Memmo Alfama",
            "description": "Boutique hotel with a rooftop pool",
            "link": "https://www.memmohotels.com/alfama",
            "property_token": "tok-memmo",
            "gps_coordinates": {"latitude": 38.7106, "longitude": -9.1316},
            "hotel_class": "4-star hotel",
            "extracted_hotel_class": 4,
            "overall_rating": 4.6,
            "reviews": 1834,
            "rate_per_night": {"lowest": "$245", "extracted_lowest": 245},
            "total_rate": {"lowest": "$980", "extracted_lowest": 980},
        },
        {
            "type": "hotel",
            "name": "Lisbon Hostel",
            "property_token": "tok-hostel",
            "gps_coordinates": {"latitude": 38.71, "longitude": -9.14},
            "overall_rating": 4.1,
            "rate_per_night": {"lowest": "$60", "extracted_lowest": 60},
        },
        {"type": "hotel", "name": "Sold Out Inn", "property_token": "tok-x"},  # no price
    ],
}


async def test_search_hotels_parses_and_sorts(monkeypatch):
    set_key(monkeypatch, "serpapi_api_key", "k")
    calls = mock_http(monkeypatch, lambda r: httpx.Response(200, json=PAYLOAD))
    hotels = await search_hotels(
        "Lisbon", date(2026, 5, 1), date(2026, 5, 5), adults=2,
        max_price_per_night=300, min_stars=3, near="Alfama",
    )

    q = calls[0].url.params
    assert (q["engine"], q["q"], q["adults"]) == ("google_hotels", "Alfama, Lisbon", "2")
    assert (q["check_in_date"], q["check_out_date"]) == ("2026-05-01", "2026-05-05")
    assert (q["hotel_class"], q["max_price"], q["currency"]) == ("3,4,5", "300", "USD")
    assert [h.id for h in hotels] == ["tok-hostel", "tok-memmo"]
    hostel, memmo = hotels
    assert hostel.total_usd == 240  # 60 * 4 nights, no total_rate
    assert memmo.address == ""
    assert (memmo.lat, memmo.lng, memmo.stars, memmo.rating) == (38.7106, -9.1316, 4, 4.6)
    assert (memmo.price_per_night_usd, memmo.total_usd) == (245, 980)
    assert memmo.booking_url == "https://www.memmohotels.com/alfama"


async def test_search_hotels_errors(monkeypatch):
    set_key(monkeypatch, "serpapi_api_key", "")
    with pytest.raises(ToolError, match="SERPAPI_API_KEY is not configured"):
        await search_hotels("Lisbon", date(2026, 5, 1), date(2026, 5, 3))
    set_key(monkeypatch, "serpapi_api_key", "k")
    mock_http(monkeypatch, lambda r: httpx.Response(400, json={"error": "Bad check_in_date"}))
    with pytest.raises(ToolError, match="400: Bad check_in_date"):
        await search_hotels("Lisbon", date(2026, 5, 1), date(2026, 5, 3))


async def test_search_hotels_cached(monkeypatch, tmp_path):
    set_key(monkeypatch, "serpapi_api_key", "k")
    calls = mock_http(monkeypatch, lambda r: httpx.Response(200, json=PAYLOAD))
    await store.init_db(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        first = await search_hotels("Lisbon", date(2026, 5, 1), date(2026, 5, 3), max_results=1)
        second = await search_hotels("Lisbon", date(2026, 5, 1), date(2026, 5, 3), max_results=1)
    finally:
        await store.close_db()
    assert len(calls) == 1
    assert first == second and len(first) == 1
