import json

import pytest

from trip_planner import store
from trip_planner.agent import service
from trip_planner.evals import run
from trip_planner.evals.judge import Criterion, JudgeScore, compact_trip
from trip_planner.trip.models import Issue

CASE = {
    "id": "lisbon",
    "message": "3 days in Lisbon from NYC, $1200, vegetarian",
    "followups": ["Use your best judgment and go ahead."],
    "expect": {
        "days": 3,
        "destinations": ["lisbon"],
        "budget_usd": 1200,
        "origin": "New York",
        "must_respect": ["Vegetarian"],
    },
}


def stop(name):
    return {"place": {"place_id": name, "name": name}, "start": "10:00", "duration_min": 60}


def make_trip(days=3, stops=2, flight=True, hotel=True, constraints=("vegetarian",)):
    return {
        "id": "t1",
        "destinations": ["Lisbon, Portugal"],
        "constraints": list(constraints),
        "flight": {
            "id": "f", "airline": "TAP", "origin": "JFK", "destination": "LIS",
            "depart_at": "2027-03-11T18:00", "arrive_at": "2027-03-12T06:00", "price_usd": 600,
        } if flight else None,
        "hotel": {
            "id": "h", "name": "Hotel", "check_in": "2027-03-12", "check_out": "2027-03-15",
            "price_per_night_usd": 100, "total_usd": 300, "booking_url": "https://x",
        } if hotel else None,
        "days": [
            {"date": f"2027-03-{12 + i}", "stops": [stop(f"s{i}{j}") for j in range(stops)]}
            for i in range(days)
        ],
    }


@pytest.fixture
def fake_checks(monkeypatch):
    """check_trip/cost_breakdown are implemented in another stream; fake them here."""
    state = {"issues": [], "total": 1000.0}
    monkeypatch.setattr(run, "check_trip", lambda trip: state["issues"])
    monkeypatch.setattr(run, "cost_breakdown", lambda trip: {"total": state["total"]})
    return state


def test_cases_file_is_valid():
    cases = run.load_cases()
    assert len(cases) == 20
    assert len({c["id"] for c in cases}) == len(cases)
    for c in cases:
        assert c["message"] and c["followups"]
        e = c["expect"]
        assert isinstance(e["days"], int) and e["days"] > 0
        assert e["destinations"]
        assert e["budget_usd"] is None or e["budget_usd"] > 0
        assert e["origin"] is None or isinstance(e["origin"], str)
        assert isinstance(e["must_respect"], list)


def test_hard_checks_pass(fake_checks):
    checks = run.hard_checks(CASE, make_trip())
    assert all(checks.values()), checks
    assert set(checks) == {
        "days", "destinations", "stops_per_day", "no_errors", "hotel", "budget", "flight",
        "respects:Vegetarian",
    }


def test_hard_checks_fail(fake_checks):
    fake_checks["issues"] = [Issue(code="closed", severity="error", message="closed")]
    fake_checks["total"] = 1500.0
    trip = make_trip(days=2, stops=1, flight=False, hotel=False, constraints=())
    trip["destinations"] = ["Porto"]
    checks = run.hard_checks(CASE, trip)
    assert not any(checks.values()), checks


def test_hard_checks_skip_optional(fake_checks):
    case = {**CASE, "expect": {**CASE["expect"], "budget_usd": None, "origin": None}}
    fake_checks["issues"] = [Issue(code="w", severity="warning", message="w")]
    checks = run.hard_checks(case, make_trip(flight=False))
    assert "budget" not in checks and "flight" not in checks
    assert all(checks.values())


def test_cost_usd():
    usage = {
        "claude-sonnet-5-5-20260901": {
            "input_tokens": 1_000_000, "output_tokens": 100_000,
            "input_token_details": {"cache_read": 500_000},
        },
        "claude-opus-5-5": {"input_tokens": 1_000_000, "output_tokens": 0},
        "unknown-model": {"input_tokens": 9_999_999, "output_tokens": 9_999_999},
    }
    # sonnet: 0.5M*2 + 0.5M*0.2 + 0.1M*10 = 2.1 ; opus: 4
    assert run.cost_usd(usage) == pytest.approx(6.1)


def test_compact_trip_drops_noise():
    out = compact_trip(make_trip())
    assert "id" not in out and "booking_url" not in out["hotel"]
    assert "place_id" not in out["days"][0]["stops"][0]["place"]


def score(overall):
    c = Criterion(score=overall, rationale="ok")
    return JudgeScore(
        fit_to_request=c, geography_and_sequencing=c, specificity=c, pacing=c, honesty=c,
        overall=overall, biggest_problem="none",
    )


async def test_runner_end_to_end(monkeypatch, tmp_path, fake_checks):
    sent: dict[str, list[str]] = {}

    async def new_trip(user_id="local"):
        tid = f"trip{len(sent)}"
        sent[tid] = []
        return tid

    async def run_turn(trip_id, message, user_id="local"):
        sent[trip_id].append(message)
        if "boom" in message:
            raise RuntimeError("planner exploded")
        if len(sent[trip_id]) == 1:  # first turn: asks a question, plans nothing
            yield {"type": "text", "delta": "What is your budget?"}
            yield {"type": "trip", "trip": make_trip(days=0)}
        else:
            yield {"type": "tool_start", "name": "search_flights", "label": "Searching"}
            yield {"type": "tool_end", "name": "search_flights", "ok": False, "summary": "timeout"}
            yield {"type": "text", "delta": "Here is "}
            yield {"type": "text", "delta": "your trip."}
            yield {"type": "trip", "trip": make_trip()}
        yield {"type": "done"}

    async def get_thread(trip_id):
        return None

    judged = []

    async def fake_judge(case, trip, final_text):
        judged.append((case["id"], final_text))
        return score(4)

    async def init_db(url=None):
        await store_init(f"sqlite+aiosqlite:///{tmp_path}/t.db")

    store_init = store.init_db
    monkeypatch.setattr(service, "new_trip", new_trip)
    monkeypatch.setattr(service, "run_turn", run_turn)
    monkeypatch.setattr(service, "get_thread", get_thread)
    monkeypatch.setattr(run, "judge", fake_judge)
    monkeypatch.setattr(run.store, "init_db", init_db)
    monkeypatch.setattr(run, "RESULTS_DIR", tmp_path / "results")

    bad = {**CASE, "id": "bad", "message": "boom"}
    out = await run.run([bad, CASE], use_judge=True, concurrency=2)

    recs = {r["id"]: r for r in map(json.loads, out.read_text().splitlines())}
    assert set(recs) == {"bad", "lisbon"}
    assert "planner exploded" in recs["bad"]["error"]

    ok = recs["lisbon"]
    assert "error" not in ok
    assert ok["turns"] == 2
    assert [CASE["message"], CASE["followups"][0]] in sent.values()
    assert ok["final_text"] == "Here is your trip."
    assert ok["tool_errors"] == ["search_flights: timeout"]
    assert all(ok["checks"].values()), ok["checks"]
    assert ok["judge"]["overall"] == 4
    assert ok["cost_usd"] == 0 and ok["latency_s"] >= 0
    assert judged == [("lisbon", "Here is your trip.")]
