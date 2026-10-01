"""Chat with the planner in a terminal: uv run python -m trip_planner.agent.cli"""

from __future__ import annotations

import asyncio

from trip_planner import store
from trip_planner.agent import service
from trip_planner.agent.graph import close_graph


async def _print_events(events) -> dict | None:
    """Print a turn; return the approval request if the graph paused."""
    approval = None
    async for e in events:
        match e["type"]:
            case "text":
                print(e["delta"], end="", flush=True)
            case "tool_start":
                print(f"\n  · {e['label']}…", flush=True)
            case "tool_end" if not e["ok"]:
                print(f"    failed: {e['summary']}")
            case "tool_end" if e["name"] == "check_trip":
                print(f"    {e['summary']}")
            case "approval":
                approval = e
            case "error":
                print(f"\n[error] {e['message']}")
    print()
    return approval


async def main() -> None:
    await store.init_db()
    trip_id = await service.new_trip()
    print(f"Trip {trip_id}. Where and when do you want to go? (Ctrl-D to quit)")
    try:
        while True:
            try:
                text = input("\n> ").strip()
            except EOFError:
                break
            if not text:
                continue
            approval = await _print_events(service.run_turn(trip_id, text))
            while approval:
                print(f"\n{approval['summary']}\nTotal: ${approval['total_usd']:,.0f}")
                yes = input("Approve and get booking links? [y/N] ").strip().lower() == "y"
                note = "" if yes else input("What should change? ")
                approval = await _print_events(service.resume(trip_id, yes, note))
    finally:
        await close_graph()
        await store.close_db()


if __name__ == "__main__":
    asyncio.run(main())
