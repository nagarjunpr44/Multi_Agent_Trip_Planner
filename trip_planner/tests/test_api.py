import json

import pytest
from fastapi.testclient import TestClient

from trip_planner import store
from trip_planner.api import app as api
from trip_planner.config import Settings
from trip_planner.trip.models import Issue

TRIP = {"id": "t1", "title": "Lisbon", "budget_usd": 1000}


@pytest.fixture
def settings(tmp_path, monkeypatch):
    s = Settings(APP_DB_URL=f"sqlite+aiosqlite:///{tmp_path}/t.db", APP_API_KEY="")
    monkeypatch.setattr(api, "get_settings", lambda: s)
    monkeypatch.setattr(store, "get_settings", lambda: s)
    api._hits.clear()
    return s


@pytest.fixture
def client(settings, monkeypatch):
    calls = {}

    async def new_trip(user_id="local"):
        await store.upsert_trip(TRIP, user_id)
        return "t1"

    async def run_turn(trip_id, message, user_id="local"):
        calls["run_turn"] = (trip_id, message)
        yield {"type": "tool_start", "name": "search_flights", "label": "Searching flights"}
        yield {"type": "text", "delta": "Hi"}
        yield {"type": "trip", "trip": TRIP}
        yield {"type": "done"}

    async def resume(trip_id, approved, note=""):
        calls["resume"] = (trip_id, approved, note)
        yield {"type": "text", "delta": "Booked"}
        raise RuntimeError("boom")

    async def get_thread(trip_id):
        if trip_id != "t1":
            return None
        return {"trip": TRIP, "messages": [], "pending_approval": None}

    monkeypatch.setattr(api.service, "new_trip", new_trip)
    monkeypatch.setattr(api.service, "run_turn", run_turn)
    monkeypatch.setattr(api.service, "resume", resume)
    monkeypatch.setattr(api.service, "get_thread", get_thread)
    monkeypatch.setattr(
        api.check,
        "check_trip",
        lambda t: [Issue(code="missing_dates", severity="error", message="no dates")],
    )
    monkeypatch.setattr(
        api.check, "cost_breakdown", lambda t: {"total": 0, "budget": t.budget_usd}
    )
    with TestClient(api.app) as c:
        c.calls = calls
        yield c


def events(resp):
    return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]


def test_health_and_index(client):
    assert client.get("/health").json() == {"status": "ok"}
    r = client.get("/")
    assert r.status_code == 200 and "<html" in r.text
    assert client.get("/static/app.js").status_code == 200


def test_trip_crud(client):
    assert client.post("/trips").json() == {"id": "t1"}
    [row] = client.get("/trips").json()
    assert row["id"] == "t1" and row["title"] == "Lisbon" and "updated_at" in row

    got = client.get("/trips/t1").json()
    assert got["trip"]["title"] == "Lisbon"
    assert got["issues"][0]["code"] == "missing_dates"
    assert got["cost"] == {"total": 0, "budget": 1000}
    assert client.get("/trips/nope").status_code == 404

    assert client.delete("/trips/t1").status_code == 204
    assert client.delete("/trips/t1").status_code == 404


def test_message_stream_enriches_trip(client):
    r = client.post("/trips/t1/messages", json={"text": "Plan Lisbon"})
    assert r.headers["content-type"].startswith("text/event-stream")
    evs = events(r)
    assert [e["type"] for e in evs] == ["tool_start", "text", "trip", "done"]
    assert evs[2]["issues"][0]["severity"] == "error"
    assert evs[2]["cost"]["budget"] == 1000
    assert client.calls["run_turn"] == ("t1", "Plan Lisbon")


def test_approval_stream_and_error(client):
    r = client.post("/trips/t1/approval", json={"approved": False, "note": "cheaper"})
    evs = events(r)
    assert [e["type"] for e in evs] == ["text", "error"]
    assert evs[1]["message"] == "boom"
    assert client.calls["resume"] == ("t1", False, "cheaper")


def test_auth(client, settings):
    settings.app_api_key = "secret"
    assert client.get("/trips").status_code == 401
    assert client.get("/trips", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/trips", headers={"Authorization": "Bearer secret"}).status_code == 200
    assert client.get("/health").status_code == 200


def test_rate_limit(client, settings):
    settings.rate_limit_per_minute = 2
    for _ in range(2):
        assert client.post("/trips/t1/messages", json={"text": "hi"}).status_code == 200
    r = client.post("/trips/t1/messages", json={"text": "hi"})
    assert r.status_code == 429 and "rate limit" in r.json()["detail"]
