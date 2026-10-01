import datetime as dt

from trip_planner.agent import tools as agent_tools
from trip_planner.agent.tools import hours_summary, run_tool
from trip_planner.trip.models import Issue, OpenPeriod, Trip

LOUVRE = {"place_id": "p1", "name": "Louvre", "lat": 48.8606, "lng": 2.3376}
ORSAY = {"place_id": "p2", "name": "Orsay", "lat": 48.8600, "lng": 2.3266}  # ~0.8 km away
VERSAILLES = {"place_id": "p3", "name": "Versailles", "lat": 48.8049, "lng": 2.1204}


def make_state(**trip) -> dict:
    trip = Trip(**trip).model_dump(mode="json")
    places = {p["place_id"]: p for p in (LOUVRE, ORSAY, VERSAILLES)}
    return {"trip": trip, "places": places, "flight_options": {}, "hotel_options": {}}


async def call(state: dict, name: str, **args):
    ok, result, updates = await run_tool(state, name, args)
    state.update(updates)
    return ok, result


async def test_date_change_rebuilds_days_keeping_stops():
    state = make_state(destinations=["Paris"])
    assert (await call(state, "update_trip", start_date="2026-05-01", end_date="2026-05-03"))[0]
    assert state["trip"]["title"] == "Paris · May 1"
    ok, res = await call(state, "add_stop", date="2026-05-02", place_id="p1", start="10:00",
                         duration_min=90, note="art")
    assert ok, res
    await call(state, "update_trip", start_date="2026-05-02", end_date="2026-05-04")
    days = state["trip"]["days"]
    assert [d["date"] for d in days] == ["2026-05-02", "2026-05-03", "2026-05-04"]
    assert days[0]["stops"][0]["id"] == res["stop_id"]
    ok, err = await call(state, "update_trip", start_date="2026-05-05")
    assert not ok and "before" in err


async def test_select_flight_rejects_unknown_ids():
    state = make_state()
    state["flight_options"] = {"f1": {"id": "f1"}}
    ok, err = await call(state, "select_flight", option_id="nope")
    assert not ok and "f1" in err
    assert state["trip"]["flight"] is None


async def test_add_stop_rejects_unknown_place_and_missing_day():
    state = make_state(start_date=dt.date(2026, 5, 1), end_date=dt.date(2026, 5, 1))
    state["trip"]["days"] = [{"date": "2026-05-01"}]
    ok, err = await call(state, "add_stop", date="2026-05-01", place_id="invented",
                         start="10:00", duration_min=60, note="")
    assert not ok and "search_places" in err
    ok, err = await call(state, "add_stop", date="2026-05-09", place_id="p1", start="10:00",
                         duration_min=60, note="")
    assert not ok and "No day" in err


async def test_update_stop_moves_days_and_keeps_order():
    state = make_state(destinations=["Paris"])
    await call(state, "update_trip", start_date="2026-05-01", end_date="2026-05-02")
    _, a = await call(state, "add_stop", date="2026-05-01", place_id="p1", start="14:00",
                      duration_min=60, note="")
    await call(state, "add_stop", date="2026-05-02", place_id="p2", start="11:00",
               duration_min=60, note="")
    ok, _ = await call(state, "update_stop", stop_id=a["stop_id"], date="2026-05-02",
                       start="09:00")
    assert ok
    d1, d2 = state["trip"]["days"]
    assert d1["stops"] == []
    assert [s["place"]["name"] for s in d2["stops"]] == ["Louvre", "Orsay"]
    assert (await call(state, "remove_stop", stop_id=a["stop_id"]))[0]
    assert len(state["trip"]["days"][1]["stops"]) == 1


async def test_check_trip_fills_travel_and_returns_issues(monkeypatch):
    calls = []

    async def fake_minutes(a, b, mode="transit"):
        calls.append(mode)
        return 12

    monkeypatch.setattr(agent_tools.routes, "travel_minutes", fake_minutes)
    monkeypatch.setattr(agent_tools, "check_trip", lambda trip: [
        Issue(code="closed", severity="error", message="Louvre is closed on Tuesdays")
    ])
    monkeypatch.setattr(agent_tools, "cost_breakdown", lambda trip: {"total": 0})
    state = make_state(destinations=["Paris"])
    await call(state, "update_trip", start_date="2026-05-01", end_date="2026-05-01")
    for pid, start in (("p1", "09:00"), ("p2", "12:00"), ("p3", "15:00")):
        await call(state, "add_stop", date="2026-05-01", place_id=pid, start=start,
                   duration_min=60, note="")

    ok, result = await call(state, "check_trip")
    assert ok
    assert result["issues"][0]["code"] == "closed" and result["cost"] == {"total": 0}
    stops = state["trip"]["days"][0]["stops"]
    assert [s["travel_mode"] for s in stops] == [None, "walk", "transit"]
    assert [s["travel_from_prev_min"] for s in stops] == [None, 12, 12]
    assert calls == ["walk", "transit"]


async def test_tool_errors_never_raise():
    ok, err, _ = await run_tool(make_state(), "add_stop", {"date": "nope"})
    assert not ok and "date" in err
    ok, err, _ = await run_tool(make_state(), "web_search", {"query": "x"})  # stub body
    assert not ok


def test_hours_summary():
    hours = [OpenPeriod(weekday=d, open=dt.time(9), close=dt.time(17)) for d in range(5)]
    hours.append(OpenPeriod(weekday=5, open=dt.time(10), close=dt.time(14)))
    assert hours_summary(hours) == "Mon–Fri 09:00–17:00; Sat 10:00–14:00; Sun closed"
    assert hours_summary(None) == "hours unknown"
