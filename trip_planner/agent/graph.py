"""The planner graph: planner ⇄ tools loop, with an approval pause before booking.

    planner ─(tool calls)→ tools ─(request_approval)→ approval ─(no errors)→ confirm
       ↑  └─(no calls)→ END   │                        │                      │
       └──────────────────────┴────────────────────────┴──────────────────────┘

`confirm` only interrupts and applies the answer, so re-running it on resume
repeats nothing else.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any
from urllib.parse import quote_plus

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from trip_planner.agent import tools as agent_tools
from trip_planner.agent.prompts import SYSTEM_PROMPT
from trip_planner.agent.state import PlannerState
from trip_planner.config import get_settings
from trip_planner.llm import get_llm, system_message
from trip_planner.trip.models import Trip

SQLITE_CHECKPOINTS = "data/checkpoints.db"

SYSTEM = system_message(SYSTEM_PROMPT)


def _last_ai(state: dict) -> AIMessage:
    return next(m for m in reversed(state["messages"]) if isinstance(m, AIMessage))


def _approval_calls(state: dict) -> list[dict]:
    return [c for c in _last_ai(state).tool_calls if c["name"] == "request_approval"]


def _tool_message(call: dict, content: Any, ok: bool = True) -> ToolMessage:
    if not isinstance(content, str):
        content = json.dumps(content, default=str)
    return ToolMessage(
        content=content if ok else f"Error: {content}",
        tool_call_id=call["id"],
        name=call["name"],
        status="success" if ok else "error",
    )


async def _timed(state: dict, call: dict) -> tuple[bool, Any, dict, int]:
    t0 = time.monotonic()
    ok, result, changed = await agent_tools.run_tool(state, call["name"], call["args"])
    return ok, result, changed, round((time.monotonic() - t0) * 1000)


def _batches(calls: list[dict]) -> list[list[dict]]:
    """Group consecutive read-only calls; every other call is its own batch."""
    read_only = agent_tools.READ_ONLY
    out: list[list[dict]] = []
    for call in calls:
        if call["name"] in read_only and out and out[-1][0]["name"] in read_only:
            out[-1].append(call)
        else:
            out.append([call])
    return out


def _booking_links(trip: Trip) -> str:
    lines = [
        "Approved. Booking links:",
        f"Flight: {trip.flight.booking_url or 'no link'}" if trip.flight else "Flight: none",
        f"Hotel: {trip.hotel.booking_url or 'no link'}" if trip.hotel else "Hotel: none",
    ]
    city = trip.destinations[0] if trip.destinations else ""
    for day in trip.days:
        if day.stops:
            path = "/".join(quote_plus(f"{s.place.name}, {city}") for s in day.stops)
            lines.append(f"{day.date} map: https://www.google.com/maps/dir/{path}")
    return "\n".join(lines)


def build_graph(checkpointer: BaseCheckpointSaver, llm: BaseChatModel | None = None):
    model = (llm or get_llm("planner")).bind_tools(agent_tools.TOOL_SCHEMAS)

    async def planner(state: PlannerState) -> dict:
        return {"messages": [await model.ainvoke([SYSTEM, *state["messages"]])]}

    async def tools(state: PlannerState) -> dict:
        write = get_stream_writer()
        work, updates, messages = dict(state), {}, []
        calls = [c for c in state["messages"][-1].tool_calls if c["name"] != "request_approval"]
        for batch in _batches(calls):
            for call in batch:
                label = agent_tools.label(call["name"], call["args"])
                write({"type": "tool_start", "name": call["name"], "label": label})
            # Searches in a batch run concurrently on the same snapshot (they only add
            # to lookup dicts); trip edits are batches of one, run in order.
            results = await asyncio.gather(*(_timed(work, c) for c in batch))
            for call, (ok, result, changed, ms) in zip(batch, results, strict=True):
                for key, value in changed.items():
                    if key in agent_tools.LOOKUPS:  # merge, so parallel searches don't clobber
                        value = {**work.get(key, {}), **value}
                    work[key] = updates[key] = value
                summary = agent_tools.summarize(result) if ok else str(result)
                write({
                    "type": "tool_end", "name": call["name"], "ok": ok, "summary": summary,
                    "ms": ms,
                })
                messages.append(_tool_message(call, result, ok))
        return {**updates, "messages": messages}

    async def approval(state: PlannerState) -> dict:
        calls = _approval_calls(state)
        ok, result, updates = await agent_tools.run_tool(state, "check_trip", {})
        errors = [i for i in result["issues"] if i["severity"] == "error"] if ok else []
        if not ok or errors:
            content = (
                f"Not sent for approval; fix these errors first: {json.dumps(errors)}"
                if ok else f"Could not check the trip: {result}"
            )
            return {**updates, "messages": [_tool_message(c, content, False) for c in calls]}
        trip = Trip.model_validate(updates.get("trip", state["trip"]))
        trip.status = "awaiting_approval"
        trip.version += 1
        return {"trip": trip.model_dump(mode="json")}

    async def confirm(state: PlannerState) -> dict:
        calls = _approval_calls(state)
        trip = Trip.model_validate(state["trip"])
        answer = interrupt({
            "summary": calls[0]["args"].get("summary", ""),
            "total_usd": agent_tools.cost_breakdown(trip)["total"],
        })
        if answer.get("approved"):
            trip.status = "approved"
            content = _booking_links(trip)
        else:
            trip.status = "planning"
            content = f"The user declined. Their note: {answer.get('note') or '(none)'}"
        trip.version += 1
        return {
            "trip": trip.model_dump(mode="json"),
            "messages": [_tool_message(c, content) for c in calls],
        }

    def after_planner(state: PlannerState) -> str:
        return "tools" if state["messages"][-1].tool_calls else END

    def after_tools(state: PlannerState) -> str:
        return "approval" if _approval_calls(state) else "planner"

    def after_approval(state: PlannerState) -> str:
        return "confirm" if state["trip"]["status"] == "awaiting_approval" else "planner"

    g = StateGraph(PlannerState)
    g.add_node("planner", planner)
    g.add_node("tools", tools)
    g.add_node("approval", approval)
    g.add_node("confirm", confirm)
    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", after_planner, ["tools", END])
    g.add_conditional_edges("tools", after_tools, ["approval", "planner"])
    g.add_conditional_edges("approval", after_approval, ["confirm", "planner"])
    g.add_edge("confirm", "planner")
    return g.compile(checkpointer=checkpointer)


# ── Singleton with a persistent checkpointer ───────────────────────────────

_graph: CompiledStateGraph | None = None
_closer = None  # closes the checkpointer's connection / pool
_lock = asyncio.Lock()


async def get_graph() -> CompiledStateGraph:
    global _graph, _closer
    async with _lock:
        if _graph is None:
            url = get_settings().checkpoint_url
            if url.startswith("postgres"):
                from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
                from psycopg.rows import dict_row
                from psycopg_pool import AsyncConnectionPool

                pool = AsyncConnectionPool(
                    url,
                    open=False,
                    kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
                )
                await pool.open()
                saver = AsyncPostgresSaver(pool)
                await saver.setup()
                _closer = pool.close
            else:
                import aiosqlite
                from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

                os.makedirs(os.path.dirname(SQLITE_CHECKPOINTS), exist_ok=True)
                conn = await aiosqlite.connect(SQLITE_CHECKPOINTS)
                saver = AsyncSqliteSaver(conn)
                await saver.setup()
                _closer = conn.close
            _graph = build_graph(saver)
    return _graph


async def close_graph() -> None:
    global _graph, _closer
    if _closer is not None:
        await _closer()
    _graph = _closer = None
