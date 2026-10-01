import json
from datetime import time

import httpx
import pytest

from trip_planner import store
from trip_planner.tests.test_tools_http import mock_http, set_key
from trip_planner.tools import ToolError
from trip_planner.tools.places import get_place, search_places


@pytest.fixture(autouse=True)
def google_provider(monkeypatch):
    set_key(monkeypatch, "places_provider", "google")


def _period(od, oh, cd, ch, om=0, cm=0):
    return {
        "open": {"day": od, "hour": oh, "minute": om},
        "close": {"day": cd, "hour": ch, "minute": cm},
    }


MUSEUM = {
    "id": "ChIJmuseum",
    "displayName": {"text": "Museu Nacional do Azulejo", "languageCode": "pt"},
    "formattedAddress": "R. Me. Deus 4, 1900-312 Lisboa, Portugal",
    "location": {"latitude": 38.7247, "longitude": -9.1135},
    "rating": 4.6,
    "userRatingCount": 9123,
    "priceLevel": "PRICE_LEVEL_INEXPENSIVE",
    "types": ["museum", "tourist_attraction"],
    "regularOpeningHours": {
        "openNow": True,
        # Tue–Sun 10:00–18:00 (closed Monday). Google day 0 = Sunday.
        "periods": [_period(d, 10, d, 18) for d in (0, 2, 3, 4, 5, 6)],
        "weekdayDescriptions": ["Monday: Closed", "..."],
    },
    "googleMapsUri": "https://maps.google.com/?cid=1",
    "websiteUri": "https://www.museudoazulejo.gov.pt/",
}
BAR = {  # Fri and Sat 20:00 → 02:00 next day, no price level / website
    "id": "ChIJbar",
    "displayName": {"text": "Park Bar"},
    "priceLevel": "PRICE_LEVEL_VERY_EXPENSIVE",
    "regularOpeningHours": {"periods": [_period(5, 20, 6, 2), _period(6, 20, 0, 2)]},
}
ALWAYS = {
    "id": "ChIJalways",
    "displayName": {"text": "Miradouro"},
    "priceLevel": "PRICE_LEVEL_FREE",
    "regularOpeningHours": {"periods": [{"open": {"day": 0, "hour": 0, "minute": 0}}]},
}
NO_HOURS = {"id": "ChIJnohours", "displayName": {"text": "Somewhere"}}


async def test_search_places(monkeypatch):
    set_key(monkeypatch, "google_places_api_key", "pk")
    payload = {"places": [MUSEUM, BAR, ALWAYS, NO_HOURS]}
    calls = mock_http(monkeypatch, lambda r: httpx.Response(200, json=payload))
    museum, bar, always, no_hours = await search_places("tiles", "Lisbon", max_results=4)

    req = calls[0]
    assert req.method == "POST" and req.url.path == "/v1/places:searchText"
    assert json.loads(req.content) == {"textQuery": "tiles in Lisbon", "pageSize": 4}
    assert req.headers["X-Goog-Api-Key"] == "pk"
    assert req.headers["X-Goog-FieldMask"].startswith("places.id,places.displayName,")

    assert museum.name == "Museu Nacional do Azulejo"
    assert (museum.lat, museum.lng, museum.rating, museum.user_ratings) == (
        38.7247, -9.1135, 4.6, 9123
    )
    assert museum.price_level == 1
    assert museum.types == ["museum", "tourist_attraction"]
    assert museum.website == "https://www.museudoazulejo.gov.pt/"
    assert sorted(p.weekday for p in museum.hours) == [1, 2, 3, 4, 5, 6]  # no Monday
    sunday = next(p for p in museum.hours if p.weekday == 6)
    assert (sunday.open, sunday.close) == (time(10), time(18))

    assert bar.price_level == 4
    assert [(p.weekday, p.open, p.close) for p in bar.hours] == [
        (4, time(20), time(2)),
        (5, time(20), time(2)),
    ]
    assert always.price_level == 0
    assert [(p.weekday, p.open, p.close) for p in always.hours] == [
        (d, time(0), time(0)) for d in range(7)
    ]
    assert no_hours.hours is None and no_hours.price_level is None


async def test_get_place_and_cache(monkeypatch, tmp_path):
    set_key(monkeypatch, "google_places_api_key", "")
    set_key(monkeypatch, "google_maps_api_key", "mk")  # places_key falls back to it
    calls = mock_http(monkeypatch, lambda r: httpx.Response(200, json=MUSEUM))
    await store.init_db(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        place = await get_place("ChIJmuseum")
        assert await get_place("ChIJmuseum") == place
    finally:
        await store.close_db()
    assert len(calls) == 1
    assert calls[0].url.path == "/v1/places/ChIJmuseum"
    assert calls[0].headers["X-Goog-Api-Key"] == "mk"
    assert calls[0].headers["X-Goog-FieldMask"].startswith("id,displayName,")
    assert place.place_id == "ChIJmuseum" and len(place.hours) == 6


async def test_places_errors(monkeypatch):
    set_key(monkeypatch, "google_places_api_key", "")
    set_key(monkeypatch, "google_maps_api_key", "")
    with pytest.raises(ToolError, match="GOOGLE_PLACES_API_KEY is not configured"):
        await search_places("ramen", "Tokyo")
    set_key(monkeypatch, "google_places_api_key", "pk")
    error = {"error": {"code": 403, "message": "API key not valid.", "status": "PERMISSION_DENIED"}}
    mock_http(monkeypatch, lambda r: httpx.Response(403, json=error))
    with pytest.raises(ToolError, match="403: API key not valid"):
        await get_place("ChIJx")
