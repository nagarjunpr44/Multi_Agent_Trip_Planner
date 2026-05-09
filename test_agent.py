"""
Standalone smoke test — runs the full LangGraph pipeline without Postgres/Redis.
Uses MemorySaver; requires configured LLM and external provider keys for full output.

Run:
  python test_agent.py
"""
from __future__ import annotations

import asyncio
import os

# Force in-memory checkpointer BEFORE any imports
os.environ.setdefault("DATABASE_URL", "")          # triggers MemorySaver fallback
os.environ.setdefault("CHECKPOINT_DB_URL", "")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")  # won't be used

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("smoke_test")


async def main() -> None:
    from agents.graph import get_graph_sync
    from tools.registry import initialize_registry

    logger.info("Initializing tool registry...")
    initialize_registry()

    logger.info("Building graph (MemorySaver)...")
    graph = get_graph_sync()

    initial_state = {
        "session_id": "test-001",
        "user_query": (
            "Plan a 3-day trip to Tokyo for 2 people in April. "
            "Budget $3000. We love food and temples."
        ),
        "constraints": {
            "destination": "Tokyo",
            "departure_date": "2026-04-10",
            "return_date": "2026-04-13",
            "num_travelers": 2,
            "budget_usd": 3000,
            "budget_tier": "mid",
            "preferences": ["food", "culture", "temples"],
        },
        "mode": "autonomous",
        "messages": [],
        "revision_count": 0,
        "status": "running",
        "errors": [],
        "agent_timings": {},
    }

    config = {"configurable": {"thread_id": "test-001"}}

    print("\n" + "="*60)
    print("  AgenticTripPlanner — Smoke Test")
    print("="*60 + "\n")

    async for event in graph.astream_events(initial_state, config=config, version="v2"):
        ev = event.get("event", "")
        node = (event.get("metadata") or {}).get("langgraph_node", "")

        if ev == "on_chain_start" and node:
            print(f"▶  {node.replace('_node','').replace('_',' ').upper()}")
        elif ev == "on_chain_end" and node:
            output = event.get("data", {}).get("output", {})
            keys = list(output.keys()) if isinstance(output, dict) else []
            print(f"✓  {node} → {keys}")

    # Pull final state
    final = graph.get_state(config)
    state = final.values

    print("\n" + "="*60)
    print("  RESULTS")
    print("="*60)

    dest = (state.get("destination_info") or {}).get("city", "N/A")
    print(f"\nDestination: {dest}")

    itinerary = state.get("itinerary") or {}
    days = itinerary.get("days", [])
    print(f"Itinerary days: {len(days)}")
    for day in days[:3]:
        all_acts = (
            day.get("morning", []) + day.get("afternoon", []) + day.get("evening", [])
        )
        print(
            f"  Day {day.get('day_number')}: "
            f"{day.get('theme') or day.get('city')} — {len(all_acts)} activities"
        )

    val = state.get("validation_result") or {}
    print(f"\nValidation score: {val.get('score', 'N/A')}")
    print(f"Passed: {val.get('passed', 'N/A')}")

    booking = state.get("booking_result") or {}
    print(f"\nBooking ref: {booking.get('booking_reference', 'N/A')}")
    print(f"Status: {booking.get('status', 'N/A')}")
    print(f"Total estimated: ${booking.get('total_estimated_usd', 'N/A')}")
    breakdown = booking.get("price_breakdown") or {}
    if breakdown:
        print(f"  Flights: ${breakdown.get('flights_usd', 0):.2f}")
        print(f"  Hotel:   ${breakdown.get('hotel_usd', 0):.2f}")
    instructions = booking.get("booking_instructions") or []
    if instructions:
        print("Booking instructions:")
        for line in instructions[:6]:
            if line:
                print(f"  {line}")

    timings = state.get("agent_timings") or {}
    print(f"\nAgent timings (ms): {timings}")

    print("\n✅ Smoke test complete.\n")


if __name__ == "__main__":
    asyncio.run(main())
