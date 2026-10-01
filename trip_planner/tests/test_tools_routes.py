import json

import httpx
import pytest

from trip_planner import store
from trip_planner.tests.test_tools_http import mock_http, set_key
from trip_planner.tools import ToolError
from trip_planner.tools.routes import _haversine_km, estimate_minutes, travel_minutes

# Rossio → Belém, Lisbon: ~7 km apart.
ROSSIO = (38.7139, -9.1394)
BELEM = (38.6916, -9.2160)


def test_estimates():
    km = _haversine_km(ROSSIO, BELEM)
    assert 6.5 < km < 7.2
    assert estimate_minutes(ROSSIO, BELEM, "walk") == round(km * 1.3 / 4.5 * 60)
    assert estimate_minutes(ROSSIO, BELEM, "transit") == round(8 + km / 18 * 60)
    assert estimate_minutes(ROSSIO, BELEM, "drive") == round(5 + km / 25 * 60)
    assert estimate_minutes(ROSSIO, ROSSIO, "walk") == 1


async def test_travel_minutes_api(monkeypatch, tmp_path):
    set_key(monkeypatch, "google_maps_api_key", "mk")
    calls = mock_http(monkeypatch, lambda r: httpx.Response(200, json={"routes": [
        {"duration": "1234s"}
    ]}))
    await store.init_db(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        assert await travel_minutes(ROSSIO, BELEM, "walk") == 21  # ceil(1234 / 60)
        assert await travel_minutes(ROSSIO, BELEM, "walk") == 21
    finally:
        await store.close_db()
    assert len(calls) == 1
    body = json.loads(calls[0].content)
    assert body["travelMode"] == "WALK"
    assert body["origin"]["location"]["latLng"] == {"latitude": 38.7139, "longitude": -9.1394}
    assert calls[0].headers["X-Goog-FieldMask"] == "routes.duration"


async def test_travel_minutes_fallbacks(monkeypatch):
    expected = estimate_minutes(ROSSIO, BELEM, "transit")
    set_key(monkeypatch, "google_maps_api_key", "")
    calls = mock_http(monkeypatch, lambda r: httpx.Response(200, json={}))
    assert await travel_minutes(ROSSIO, BELEM) == expected
    assert calls == []  # no key: no request

    set_key(monkeypatch, "google_maps_api_key", "mk")
    assert await travel_minutes(ROSSIO, BELEM) == expected  # no routes
    mock_http(monkeypatch, lambda r: httpx.Response(500, text="boom"))
    assert await travel_minutes(ROSSIO, BELEM) == expected

    with pytest.raises(ToolError, match="Unknown travel mode"):
        await travel_minutes(ROSSIO, BELEM, "fly")
