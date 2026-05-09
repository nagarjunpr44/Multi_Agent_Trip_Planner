"""
End-to-end trip planner test — runs the full LangGraph pipeline and
prints a richly-formatted trip plan to the terminal.

Usage:
    .venv/bin/python test_e2e.py
"""
from __future__ import annotations

import asyncio
import os
import textwrap
from typing import Any

# ── Environment ────────────────────────────────────────────────────────────
os.environ.setdefault("DATABASE_URL", "")          # MemorySaver
os.environ.setdefault("CHROMA_HOST", "embedded")

import logging

logging.basicConfig(
    level=logging.WARNING,  # suppress noise; we print our own output
    format="%(levelname)s %(name)s: %(message)s",
)

# ── Trip request ───────────────────────────────────────────────────────────
TRIP_REQUEST = {
    "user_query": (
        "Plan a 5-day trip to Tokyo for 2 people in April 2026. "
        "We love street food, anime culture, and hidden neighbourhoods. "
        "Mid-range budget, flying from San Francisco."
    ),
    "constraints": {
        "destinations": ["Tokyo"],
        "origin_city": "San Francisco",
        "num_travelers": 2,
        "duration_days": 5,
        "departure_date": "2026-04-10",
        "return_date": "2026-04-15",
        "budget_usd": 4000,
        "budget_tier": "mid",
        "activity_preferences": ["street food", "anime", "local neighborhoods", "hidden gems"],
        "dietary_restrictions": [],
    },
}

# ── Helpers ────────────────────────────────────────────────────────────────

W = 70  # terminal width

def banner(text: str, char: str = "═") -> str:
    return f"\n{char * W}\n  {text}\n{char * W}"

def section(title: str) -> str:
    return f"\n{'─' * W}\n  {title}\n{'─' * W}"

def bullet(items: list[str], indent: int = 4) -> str:
    prefix = " " * indent + "• "
    return "\n".join(prefix + i for i in items) if items else " " * indent + "(none)"

def wrap(text: str, indent: int = 4) -> str:
    return textwrap.fill(text, width=W, initial_indent=" " * indent,
                         subsequent_indent=" " * indent)


# ── Main ───────────────────────────────────────────────────────────────────

async def main() -> None:

    from agents.graph import get_graph_sync
    from tools.registry import initialize_registry

    print(banner("AgenticTripPlanner — End-to-End Test", "═"))
    print(f"\n  Query: {TRIP_REQUEST['user_query'][:80]}...")

    initialize_registry()
    graph = get_graph_sync()

    initial_state = {
        "session_id": "e2e-001",
        "user_query": TRIP_REQUEST["user_query"],
        "constraints": TRIP_REQUEST["constraints"],
        "mode": "autonomous",
        "messages": [],
        "revision_count": 0,
        "status": "running",
        "errors": [],
        "agent_timings": {},
    }

    config = {"configurable": {"thread_id": "e2e-001"}}

    # ── Stream events ──────────────────────────────────────────────────────
    print(section("Running agents..."))
    final_state: dict[str, Any] = {}

    started_nodes: set[str] = set()
    completed_nodes: set[str] = set()

    async for event in graph.astream_events(initial_state, config=config, version="v2"):
        ev = event.get("event", "")
        node = (event.get("metadata") or {}).get("langgraph_node", "")

        if ev == "on_chain_start" and node and node not in started_nodes:
            started_nodes.add(node)
            print(f"  ▶  {node:<30}  starting...")

        elif ev == "on_chain_end" and node and node not in completed_nodes:
            output = event.get("data", {}).get("output", {})
            if isinstance(output, dict) and output:
                completed_nodes.add(node)
                keys = [k for k in output if not k.startswith("_")]
                print(f"  ✓  {node:<30}  → {keys}")
                final_state.update(output)

    # ── Print trip plan ────────────────────────────────────────────────────
    print(banner("TRIP PLAN RESULTS", "═"))

    # Destination info
    dest_info = final_state.get("destination_info") or {}
    if dest_info:
        print(section(f"DESTINATION: {dest_info.get('destination', 'Tokyo').upper()}"))
        print(wrap(dest_info.get("current_weather_summary", "")))
        print()
        highlights = dest_info.get("highlights") or []
        if highlights:
            print("  Highlights:")
            print(bullet(highlights))
        tips = dest_info.get("local_tips") or []
        if tips:
            print("\n  Local Tips:")
            print(bullet(tips[:4]))

    # Flights
    flights = final_state.get("flight_results") or {}
    options = flights.get("options") or []
    if options:
        print(section("FLIGHTS"))
        for i, f in enumerate(options[:3], 1):
            airline = f.get("airline", "Unknown")
            dep = f.get("departure_time", "")[:16]
            arr = f.get("arrival_time", "")[:16]
            price = f.get("price_usd", 0)
            stops = f.get("stops", 0)
            stops_str = "Direct" if stops == 0 else f"{stops} stop(s)"
            print(f"  {i}. {airline:<20} {dep} → {arr}  ${price:,.0f}/person  {stops_str}")

    # Hotels
    hotels = final_state.get("hotel_results") or {}
    h_options = hotels.get("options") or []
    if h_options:
        print(section("HOTELS"))
        for i, h in enumerate(h_options[:3], 1):
            name = h.get("name", "Unknown")
            stars = "★" * int(h.get("star_rating", 3))
            price = h.get("price_per_night_usd", 0)
            area = h.get("neighborhood", h.get("city", ""))
            print(f"  {i}. {name:<28} {stars:<6} ${price:,.0f}/night  {area}")

    # Budget
    budget = final_state.get("budget_analysis") or {}
    if budget:
        print(section("BUDGET SUMMARY"))
        mid = budget.get("mid") or {}
        rec_tier = budget.get("recommended_tier", "mid")
        total = mid.get("total_usd", 0)
        print(f"  Recommended tier : {rec_tier.upper()}")
        travelers = TRIP_REQUEST["constraints"]["num_travelers"]
        print(f"  Estimated total  : ${total:,.0f} for {travelers} travelers")
        tips = budget.get("savings_tips") or []
        if tips:
            print("\n  Savings Tips:")
            print(bullet(tips[:3]))

    # Itinerary
    itinerary = final_state.get("itinerary") or {}
    days = itinerary.get("days") or []
    if days:
        print(section("DAY-BY-DAY ITINERARY"))
        for day in days:
            day_num = day.get("day_number", "?")
            theme = day.get("theme") or f"Day {day_num}"
            date_ = day.get("date", "")
            print(f"\n  Day {day_num} — {theme}  {('(' + date_ + ')') if date_ else ''}")
            for period, label in [
                ("morning", "Morning"),
                ("afternoon", "Afternoon"),
                ("evening", "Evening"),
            ]:
                activities = day.get(period) or []
                if activities:
                    print(f"    {label}:")
                    for act in activities:
                        name = act.get("name", "")
                        dur = act.get("duration_minutes", 0)
                        cost = act.get("cost_usd", 0)
                        cost_str = f"  ${cost:.0f}" if cost else "  Free"
                        dur_str = f"  {dur}min" if dur else ""
                        print(f"      • {name}{dur_str}{cost_str}")

    # Experiences
    experiences = final_state.get("experience_results") or []
    if experiences:
        print(section("TOP EXPERIENCES"))
        restaurants = [e for e in experiences if e.get("category") == "restaurant"][:3]
        attractions = [e for e in experiences if e.get("category") == "attraction"][:3]
        hidden = [e for e in experiences if e.get("category") == "hidden_gem"][:2]

        if restaurants:
            print("  Restaurants:")
            for r in restaurants:
                rating = r.get("rating")
                rating_str = f"  ★{rating:.1f}" if rating else ""
                print(f"    • {r.get('name')}{rating_str} — {r.get('description', '')[:60]}")
        if attractions:
            print("\n  Must-See Attractions:")
            for a in attractions:
                print(f"    • {a.get('name')} — {a.get('description', '')[:60]}")
        if hidden:
            print("\n  Hidden Gems:")
            for h in hidden:
                print(f"    • {h.get('name')} — {h.get('description', '')[:60]}")

    # Validation
    validation = final_state.get("validation_result") or {}
    if validation:
        print(section("PLAN VALIDATION"))
        score = validation.get("score", 0)
        passed = validation.get("passed", False)
        status_str = "✅ PASSED" if passed else "⚠️  NEEDS REVIEW"
        print(f"  Overall score : {score:.0%}  {status_str}")
        for key, label in [
            ("feasibility_score", "Feasibility"),
            ("budget_alignment_score", "Budget fit"),
            ("coverage_score", "Coverage"),
            ("quality_score", "Quality"),
        ]:
            v = validation.get(key, 1.0)
            bar = "█" * int(v * 10) + "░" * (10 - int(v * 10))
            print(f"  {label:<20} {bar}  {v:.0%}")
        issues = validation.get("issues") or []
        if issues:
            print("\n  Issues flagged:")
            print(bullet(issues))

    # Booking
    booking = final_state.get("booking_result") or {}
    if booking:
        print(section("BOOKING CONFIRMATION"))
        print(f"  Reference : {booking.get('booking_reference', 'N/A')}")
        print(f"  Status    : {booking.get('status', 'unknown').upper()}")
        charged = booking.get("total_charged_usd", 0)
        if charged:
            print(f"  Charged   : ${charged:,.2f}")
        details = booking.get("confirmation_details")
        if details:
            print(wrap(details))

    # Timings
    timings = final_state.get("agent_timings") or {}
    if timings:
        print(section("AGENT TIMINGS"))
        for agent, ms in sorted(timings.items(), key=lambda x: -x[1]):
            bar = "▪" * min(int(ms / 500), 30)
            print(f"  {agent:<20} {ms:>6,.0f}ms  {bar}")

    total_ms = sum(timings.values())
    print(f"\n  Total wall time : {total_ms / 1000:.1f}s")
    print(banner("DONE ✅", "═"))


if __name__ == "__main__":
    asyncio.run(main())
