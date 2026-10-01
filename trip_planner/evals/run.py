"""Run the eval cases against the real planner.

    uv run python -m trip_planner.evals.run [--case ID ...] [--limit N]
                                            [--no-judge] [--concurrency 2]

One JSON line per case goes to trip_planner/evals/results/<UTC timestamp>.jsonl.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from langchain_core.callbacks import get_usage_metadata_callback

from trip_planner import store
from trip_planner.agent import service
from trip_planner.evals.judge import judge
from trip_planner.trip.check import check_trip, cost_breakdown
from trip_planner.trip.models import Trip

HERE = Path(__file__).parent
RESULTS_DIR = HERE / "results"
MAX_EXTRA_TURNS = 2

# USD per 1M tokens (input, output). Cache reads are billed at 10% of input.
# Add your models' current prices here; runs using an unpriced model report cost as n/a.
PRICES = {
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-opus-5-5": (4.0, 20.0),
}


def load_cases() -> list[dict]:
    return json.loads((HERE / "cases.json").read_text())


def filled_days(trip: dict) -> int:
    return sum(1 for day in trip.get("days", []) if day.get("stops"))


def hard_checks(case: dict, trip_dict: dict) -> dict[str, bool]:
    trip = Trip.model_validate(trip_dict)
    exp = case["expect"]
    have = " | ".join(trip.destinations).lower()
    # The arrival day may legitimately be light (late flight, check-in only).
    arrival = trip.flight.arrive_at.date() if trip.flight else None
    full_days = [d for d in trip.days if d.date != arrival]
    checks = {
        "days": len(trip.days) == exp["days"],
        "destinations": all(d.lower() in have for d in exp["destinations"]),
        "stops_per_day": bool(full_days) and all(len(d.stops) >= 2 for d in full_days),
        "no_errors": not any(i.severity == "error" for i in check_trip(trip)),
        "hotel": trip.hotel is not None,
    }
    if exp["budget_usd"] is not None:
        checks["budget"] = cost_breakdown(trip)["total"] <= exp["budget_usd"]
    if exp["origin"]:
        checks["flight"] = trip.flight is not None
    said = " | ".join(trip.constraints + trip.prefs).lower()
    for c in exp["must_respect"]:
        checks[f"respects:{c}"] = c.lower() in said
    return checks


def cost_usd(usage: dict) -> float | None:
    """Estimated cost, or None when any model used has no entry in PRICES."""
    total = 0.0
    for model, u in usage.items():
        price = next((p for name, p in PRICES.items() if model.startswith(name)), None)
        if price is None:
            return None
        p_in, p_out = price
        cached = (u.get("input_token_details") or {}).get("cache_read") or 0
        total += (u["input_tokens"] - cached) * p_in + cached * p_in * 0.1
        total += u["output_tokens"] * p_out
    return round(total / 1e6, 4)


async def run_case(case: dict, use_judge: bool) -> dict:
    rec: dict = {"id": case["id"], "turns": 0, "tool_errors": [], "trip": {}, "final_text": ""}
    start = time.monotonic()
    # Usage is tracked per model and includes the judge (Opus) when it runs.
    with get_usage_metadata_callback() as cb:
        try:
            trip_id = await service.new_trip()
            messages = [case["message"], *case["followups"][:MAX_EXTRA_TURNS]]
            for i, message in enumerate(messages):
                if i and filled_days(rec["trip"]) >= case["expect"]["days"]:
                    break
                rec["turns"] += 1
                text = ""
                async for ev in service.run_turn(trip_id, message):
                    if ev["type"] == "text":
                        text += ev["delta"]
                    elif ev["type"] == "trip":
                        rec["trip"] = ev["trip"]
                    elif ev["type"] == "tool_end" and not ev["ok"]:
                        rec["tool_errors"].append(f"{ev['name']}: {ev['summary']}")
                    elif ev["type"] == "error":
                        rec["error"] = ev["message"]
                rec["final_text"] = text or rec["final_text"]
            if not rec["trip"]:
                thread = await service.get_thread(trip_id)
                rec["trip"] = (thread or {}).get("trip") or {}
            rec["latency_s"] = round(time.monotonic() - start, 1)
            rec["checks"] = hard_checks(case, rec["trip"])
            if use_judge:
                score = await judge(case, rec["trip"], rec["final_text"])
                rec["judge"] = score.model_dump()
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"
        rec.setdefault("latency_s", round(time.monotonic() - start, 1))
        rec["usage"] = cb.usage_metadata
        rec["cost_usd"] = cost_usd(cb.usage_metadata)
    return rec


def print_summary(records: list[dict]) -> None:
    print(
        f"\n{'case':34} {'checks':>7} {'judge':>5} {'tool_err':>8} {'lat_s':>7} "
        f"{'tokens':>9} {'cost_$':>7}"
    )
    for r in records:
        checks = r.get("checks", {})
        passed = f"{sum(checks.values())}/{len(checks)}" if checks else "-"
        overall = r.get("judge", {}).get("overall", "-")
        print(
            f"{r['id'][:34]:34} {passed:>7} {overall:>5} {len(r['tool_errors']):>8} "
            f"{r['latency_s']:>7.1f} {_tokens(r):>9,} {_money(r['cost_usd']):>7}"
            + (f"  ERROR {r['error'][:60]}" if "error" in r else "")
        )
    n = len(records) or 1
    checks = [v for r in records for v in r.get("checks", {}).values()]
    judged = [r["judge"]["overall"] for r in records if "judge" in r]
    print(
        f"\n{len(records)} cases, {sum('error' in r for r in records)} errored | "
        f"checks {sum(checks)}/{len(checks)} | "
        f"judge mean {sum(judged) / len(judged) if judged else 0:.2f} ({len(judged)} judged) | "
        f"tool errors {sum(len(r['tool_errors']) for r in records)} | "
        f"latency mean {sum(r['latency_s'] for r in records) / n:.1f}s | "
        f"tokens {sum(_tokens(r) for r in records):,} | "
        f"cost total {_money(_total_cost(records))}"
    )


def _tokens(r: dict) -> int:
    return sum(u.get("total_tokens", 0) for u in (r.get("usage") or {}).values())


def _total_cost(records: list[dict]) -> float | None:
    costs = [r["cost_usd"] for r in records]
    return None if None in costs else sum(costs)


def _money(v: float | None) -> str:
    return "n/a" if v is None else f"${v:.3f}"


async def run(cases: list[dict], use_judge: bool = True, concurrency: int = 2) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}.jsonl"
    sem = asyncio.Semaphore(concurrency)

    async def one(case: dict) -> dict:
        async with sem:
            rec = await run_case(case, use_judge)
            with out.open("a") as f:  # written as each case finishes
                f.write(json.dumps(rec, default=str) + "\n")
            print(f"done {rec['id']}", flush=True)
            return rec

    await store.init_db()
    try:
        records = await asyncio.gather(*(one(c) for c in cases))
    finally:
        await store.close_db()
    print_summary(records)
    print(f"\nresults: {out}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--case", action="append", default=[], help="case id (repeatable)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--concurrency", type=int, default=2)
    args = ap.parse_args()

    cases = load_cases()
    if args.case:
        unknown = set(args.case) - {c["id"] for c in cases}
        if unknown:
            ap.error(f"unknown case ids: {', '.join(sorted(unknown))}")
        cases = [c for c in cases if c["id"] in args.case]
    cases = cases[: args.limit]

    print(f"WARNING: runs the real planner{'' if args.no_judge else ' and Opus judge'} on "
          f"{len(cases)} case(s); this calls paid APIs and can cost several dollars per case.")
    asyncio.run(run(cases, use_judge=not args.no_judge, concurrency=args.concurrency))


if __name__ == "__main__":
    main()
