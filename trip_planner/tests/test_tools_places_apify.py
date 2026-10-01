import json
from datetime import time

import httpx
import pytest

from trip_planner import store
from trip_planner.tests.test_tools_http import mock_http, set_key
from trip_planner.tools import ToolError
from trip_planner.tools.places import get_place, search_many, search_places
from trip_planner.tools.places_apify import parse_hours

WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
ITEM = {
    "placeId": "ChIJkim",
    "title": "Kim's Island",
    "address": "175 Main St, Staten Island, NY 10307",
    "location": {"lat": 40.51, "lng": -74.24},
    "totalScore": 4.5,
    "reviewsCount": 91,
    "price": "$$",
    "categoryName": "Chinese restaurant",
    "categories": ["Chinese restaurant", "Delivery Restaurant"],
    "openingHours": [{"day": d, "hours": "11 AM to 9:30 PM"} for d in WEEK[1:]]
    + [{"day": "Monday", "hours": "Closed"}],
    "url": "https://www.google.com/maps/place/kim",
    "website": "http://kimsislandsi.com/",
    "permanentlyClosed": False,
}


@pytest.fixture(autouse=True)
def apify(monkeypatch):
    set_key(monkeypatch, "places_provider", "apify")
    set_key(monkeypatch, "apify_api_token", "apify_api_test")


def _hours(*rows):
    return parse_hours([{"day": d, "hours": h} for d, h in rows])


def test_parse_hours_formats():
    assert _hours(("Monday", "11 AM to 9:30 PM")) == [
        _p(0, time(11), time(21, 30))
    ]
    assert _hours(("Tuesday", "11 AM to 3 PM, 5 to 10 PM")) == [
        _p(1, time(11), time(15)), _p(1, time(17), time(22))
    ]
    assert _hours(("Wednesday", "11 to 2 PM")) == [_p(2, time(11), time(14))]
    assert _hours(("Friday", "6 PM to 2 AM")) == [_p(4, time(18), time(2))]  # past midnight
    assert _hours(("Saturday", "12 PM to 12 AM")) == [_p(5, time(12), time(0))]
    assert _hours(("Sunday", "Open 24 hours")) == [_p(6, time(0), time(0))]
    assert _hours(("Monday", "Closed"), ("Tuesday", "9 AM–5 PM")) == [_p(1, time(9), time(17))]
    assert _hours(("Thursday", "09:00 to 17:30")) == [_p(3, time(9), time(17, 30))]


def test_parse_hours_unknown_is_none_not_closed():
    # One unparseable day makes all hours unknown, so check_trip never flags a false "closed".
    assert _hours(("Monday", "9 AM to 5 PM"), ("Tuesday", "Hours might differ")) is None
    assert _hours(("Someday", "9 AM to 5 PM")) is None
    assert parse_hours(None) is None and parse_hours([]) is None


def _p(weekday, open_, close):
    from trip_planner.trip.models import OpenPeriod

    return OpenPeriod(weekday=weekday, open=open_, close=close)


async def test_search_places_maps_items_and_sends_detail_scrape(monkeypatch):
    closed = {**ITEM, "placeId": "ChIJgone", "permanentlyClosed": True}
    calls = mock_http(monkeypatch, lambda r: httpx.Response(201, json=[ITEM, closed, {"x": 1}]))
    places = await search_places("chinese food", "Staten Island", 3)

    assert [p.place_id for p in places] == ["ChIJkim"]  # closed + id-less items dropped
    p = places[0]
    assert (p.name, p.rating, p.user_ratings, p.price_level) == ("Kim's Island", 4.5, 91, 2)
    assert (p.lat, p.lng, p.maps_url) == (40.51, -74.24, "https://www.google.com/maps/place/kim")
    assert p.types == ["Chinese restaurant", "Delivery Restaurant"]
    assert len(p.hours) == 6 and all(h.weekday != 0 for h in p.hours)  # closed Mondays

    req = calls[0]
    assert req.url.path.endswith("compass~crawler-google-places/run-sync-get-dataset-items")
    assert req.headers["Authorization"] == "Bearer apify_api_test"
    body = json.loads(req.content)
    assert body["searchStringsArray"] == ["chinese food"]
    assert body["locationQuery"] == "Staten Island"
    assert body["maxCrawledPlacesPerSearch"] == 3
    assert body["scrapePlaceDetailPage"] is True


async def test_get_place_by_id_and_cache(monkeypatch, tmp_path):
    calls = mock_http(monkeypatch, lambda r: httpx.Response(201, json=[ITEM]))
    await store.init_db(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        assert (await get_place("ChIJkim")).name == "Kim's Island"
        await get_place("ChIJkim")
    finally:
        await store.close_db()
    assert len(calls) == 1  # second call served from cache
    assert json.loads(calls[0].content)["placeIds"] == ["ChIJkim"]


async def test_price_ranges_are_unknown_level(monkeypatch):
    mock_http(monkeypatch, lambda r: httpx.Response(201, json=[{**ITEM, "price": "$10–20"}]))
    assert (await search_places("x", "y"))[0].price_level is None


async def test_errors(monkeypatch):
    set_key(monkeypatch, "apify_api_token", "")
    with pytest.raises(ToolError, match="APIFY_API_TOKEN is not configured"):
        await search_places("x", "y")
    set_key(monkeypatch, "apify_api_token", "t")
    mock_http(monkeypatch, lambda r: httpx.Response(
        402, json={"error": {"type": "not-enough-usage", "message": "Not enough credits"}}
    ))
    with pytest.raises(ToolError, match="Apify error 402: Not enough credits"):
        await search_places("x", "y")
    mock_http(monkeypatch, lambda r: httpx.Response(201, json=[]))
    with pytest.raises(ToolError, match="No place found"):
        await get_place("ChIJnone")


async def test_search_many_is_one_run_and_dedupes(monkeypatch):
    other = {**ITEM, "placeId": "ChIJother", "title": "Other"}
    calls = mock_http(monkeypatch, lambda r: httpx.Response(201, json=[ITEM, other, ITEM]))
    found = await search_many(["chinese food", "dumplings"], "Staten Island", 4)
    assert [p.place_id for p in found] == ["ChIJkim", "ChIJother"]
    assert len(calls) == 1
    body = json.loads(calls[0].content)
    assert body["searchStringsArray"] == ["chinese food", "dumplings"]
    assert body["maxCrawledPlacesPerSearch"] == 4
