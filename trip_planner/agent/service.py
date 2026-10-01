"""Public entry points of the planner (used by the API, CLI and evals).

Event stream contract (dicts yielded by run_turn):
    {"type": "text", "delta": str}                       planner's visible text, streamed
    {"type": "tool_start", "name": str, "label": str}    e.g. label "Searching flights LIS → NRT"
    {"type": "tool_end", "name": str, "ok": bool, "summary": str, "ms": int}
    {"type": "trip", "trip": dict}                       full Trip after any change
    {"type": "approval", "summary": str, "total_usd": float}   graph paused for approval
    {"type": "done"}
    {"type": "error", "message": str}
"""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from trip_planner import store
from trip_planner.agent.graph import get_graph
from trip_planner.agent.prompts import strip_context, user_message
from trip_planner.trip.models import Trip

RECURSION_LIMIT = 80


def _config(trip_id: str) -> dict:
    return {"configurable": {"thread_id": trip_id}, "recursion_limit": RECURSION_LIMIT}


def _text(content: Any) -> str:
    """Visible text only: skips thinking and tool_use blocks."""
    if isinstance(content, str):
        return content
    return "".join(
        b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
    )


def _error(e: Exception) -> dict:
    return {"type": "error", "message": str(e) or type(e).__name__}


async def new_trip(user_id: str = "local") -> str:
    """Create an empty Trip + thread. Returns the trip id (also the LangGraph thread_id)."""
    trip = Trip()
    await store.upsert_trip(trip.model_dump(mode="json"), user_id=user_id)
    return trip.id


async def run_turn(trip_id: str, message: str, user_id: str = "local") -> AsyncIterator[dict]:
    """Send a user message and stream events until the planner finishes or pauses."""
    try:
        state = await (await get_graph()).aget_state(_config(trip_id))
        if state.interrupts:
            # A message while approval is pending means "not yet": the pending
            # request_approval call must be answered before the planner runs again.
            async for event in resume(trip_id, approved=False, note=message):
                yield event
            return
        if state.values:
            trip, graph_input = state.values["trip"], {}
        else:
            row = await store.get_trip(trip_id)
            if row is None:
                yield {"type": "error", "message": f"Unknown trip {trip_id}"}
                return
            trip = row["trip"]
            graph_input = {
                "trip": trip, "flight_options": {}, "hotel_options": {}, "places": {},
                "user_id": user_id,
            }
        prefs = await store.get_preferences(user_id)
        text = user_message(message, Trip.model_validate(trip), prefs, dt.date.today())
        graph_input["messages"] = [HumanMessage(text)]
    except Exception as e:
        yield _error(e)
        return
    async for event in _stream(trip_id, graph_input):
        yield event


async def resume(trip_id: str, approved: bool, note: str = "") -> AsyncIterator[dict]:
    """Answer a pending approval and stream the rest of the turn."""
    try:
        state = await (await get_graph()).aget_state(_config(trip_id))
    except Exception as e:
        yield _error(e)
        return
    if not state.interrupts:
        yield {"type": "error", "message": "No approval is pending for this trip"}
        return
    async for event in _stream(trip_id, Command(resume={"approved": approved, "note": note})):
        yield event


async def _stream(trip_id: str, graph_input: Any) -> AsyncIterator[dict]:
    try:
        graph = await get_graph()
        config = _config(trip_id)
        last_trip = None
        async for mode, chunk in graph.astream(
            graph_input, config, stream_mode=["messages", "custom", "updates"]
        ):
            if mode == "messages":
                msg, meta = chunk
                if meta.get("langgraph_node") == "planner" and isinstance(msg, AIMessage):
                    if delta := _text(msg.content):
                        yield {"type": "text", "delta": delta}
            elif mode == "custom":
                yield chunk
            else:
                for node, update in chunk.items():
                    if node == "__interrupt__":
                        for intr in update:
                            yield {"type": "approval", **intr.value}
                    elif update and "trip" in update and update["trip"] != last_trip:
                        last_trip = update["trip"]
                        yield {"type": "trip", "trip": last_trip}
        values = (await graph.aget_state(config)).values
        await store.upsert_trip(values["trip"], user_id=values.get("user_id", "local"))
        yield {"type": "done"}
    except Exception as e:
        yield _error(e)


async def get_thread(trip_id: str) -> dict | None:
    """{"trip": dict, "messages": [{"role": "user"|"assistant", "text": str}],
    "pending_approval": {"summary", "total_usd"} | None}  or None if unknown."""
    state = await (await get_graph()).aget_state(_config(trip_id))
    if not state.values:
        row = await store.get_trip(trip_id)
        if row is None:
            return None
        return {"trip": row["trip"], "messages": [], "pending_approval": None}
    messages = []
    for m in state.values["messages"]:
        if isinstance(m, HumanMessage):
            messages.append({"role": "user", "text": strip_context(_text(m.content))})
        elif isinstance(m, AIMessage) and (text := _text(m.content)):
            messages.append({"role": "assistant", "text": text})
    return {
        "trip": state.values["trip"],
        "messages": messages,
        "pending_approval": state.interrupts[0].value if state.interrupts else None,
    }
