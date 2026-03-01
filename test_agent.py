"""
Standalone smoke test — runs the full LangGraph pipeline without Postgres/Redis.
Uses MemorySaver + MOCK_FALLBACK so zero services needed.

Run:
  python test_agent.py
"""
from __future__ import annotations

import asyncio
import os

# Force mock mode + in-memory checkpointer BEFORE any imports
os.environ.setdefault("MOCK_FALLBACK", "true")
os.environ.setdefault("DATABASE_URL", "")          # triggers MemorySaver fallback
os.environ.setdefault("CHECKPOINT_DB_URL", "")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")  # won't be used

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("smoke_test")


async def main() -> None:
    from tools.registry import initialize_registry
    from agents.graph import reset_graph, get_graph_sync

    logger.info("Initializing tool registry...")
    initialize_registry()

    logger.info("Building graph (MemorySaver)...")
    graph = get_graph_sync()

    initial_state = {
        "session_id": "test-001",
        "user_query": "Plan a 3-day trip to Tokyo for 2 people in April. Budget $3000. We love food and temples.",
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
        print(f"  Day {day.get('day_number')}: {day.get('theme')} — {len(day.get('activities', []))} activities")

    val = state.get("validation_result") or {}
    print(f"\nValidation score: {val.get('score', 'N/A')}")
    print(f"Passed: {val.get('passed', 'N/A')}")

    booking = state.get("booking_result") or {}
    print(f"\nBooking ref: {booking.get('booking_reference', 'N/A')}")
    print(f"Total charged: ${booking.get('total_charged_usd', 'N/A')}")

    timings = state.get("agent_timings") or {}
    print(f"\nAgent timings (ms): {timings}")

    print("\n✅ Smoke test complete.\n")


if __name__ == "__main__":
    asyncio.run(main())
