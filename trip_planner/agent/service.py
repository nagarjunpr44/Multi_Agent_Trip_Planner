"""Public entry points of the planner (used by the API, CLI and evals).

Event stream contract (dicts yielded by run_turn):
    {"type": "text", "delta": str}                       planner's visible text, streamed
    {"type": "tool_start", "name": str, "label": str}    e.g. label "Searching flights LIS → NRT"
    {"type": "tool_end", "name": str, "ok": bool, "summary": str}
    {"type": "trip", "trip": dict}                       full Trip after any change
    {"type": "approval", "summary": str, "total_usd": float}   graph paused for approval
    {"type": "done"}
    {"type": "error", "message": str}
"""

from __future__ import annotations

from collections.abc import AsyncIterator


async def new_trip(user_id: str = "local") -> str:
    """Create an empty Trip + thread. Returns the trip id (also the LangGraph thread_id)."""
    raise NotImplementedError


async def run_turn(trip_id: str, message: str, user_id: str = "local") -> AsyncIterator[dict]:
    """Send a user message and stream events until the planner finishes or pauses."""
    raise NotImplementedError
    yield {}


async def resume(trip_id: str, approved: bool, note: str = "") -> AsyncIterator[dict]:
    """Answer a pending approval and stream the rest of the turn."""
    raise NotImplementedError
    yield {}


async def get_thread(trip_id: str) -> dict | None:
    """{"trip": dict, "messages": [{"role": "user"|"assistant", "text": str}],
    "pending_approval": {"summary", "total_usd"} | None}  or None if unknown."""
    raise NotImplementedError
