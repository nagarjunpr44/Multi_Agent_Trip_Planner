import json
import re

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from langgraph.checkpoint.memory import InMemorySaver

from trip_planner import store
from trip_planner.agent import graph as graph_mod
from trip_planner.agent import service
from trip_planner.agent import tools as agent_tools
from trip_planner.trip.models import Place


class ScriptedModel(GenericFakeChatModel):
    """Replays AIMessages (with tool calls), streaming text word by word."""

    def bind_tools(self, tools, **kwargs):
        return self

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        msg = next(self.messages)
        chunks = [AIMessageChunk(content=t) for t in re.split(r"(\s)", msg.content) if t]
        chunks.append(AIMessageChunk(content="", tool_call_chunks=[
            {"name": c["name"], "args": json.dumps(c["args"]), "id": c["id"], "index": i}
            for i, c in enumerate(msg.tool_calls)
        ]))
        for chunk in (ChatGenerationChunk(message=c) for c in chunks):
            if run_manager:
                run_manager.on_llm_new_token(chunk.message.content, chunk=chunk)
            yield chunk


def ai(text: str, *calls: tuple[str, dict]) -> AIMessage:
    return AIMessage(content=text, tool_calls=[
        {"name": n, "args": a, "id": f"call_{n}_{i}"} for i, (n, a) in enumerate(calls)
    ])


async def collect(events) -> list[dict]:
    return [e async for e in events]


async def test_plan_check_approve(tmp_path, monkeypatch):
    async def fake_search(query, near, max_results=8):
        return [Place(place_id="p1", name="MAAT", lat=38.6957, lng=-9.1926)]

    monkeypatch.setattr(agent_tools.places, "search_places", fake_search)
    monkeypatch.setattr(agent_tools, "check_trip", lambda trip: [])
    monkeypatch.setattr(agent_tools, "cost_breakdown", lambda trip: {"total": 120.0})

    model = ScriptedModel(messages=iter([
        ai("Planning Lisbon.",
           ("update_trip", {"destinations": ["Lisbon"], "start_date": "2026-05-01",
                            "end_date": "2026-05-02"}),
           ("search_places", {"query": "museum"})),
        ai("", ("add_stop", {"date": "2026-05-01", "place_id": "p1", "start": "10:00",
                             "duration_min": 90, "note": "river views"}),
           ("check_trip", {})),
        ai("All set.", ("request_approval", {"summary": "Lisbon, 2 days"})),
        ai("Approved, enjoy Lisbon!"),
    ]))
    monkeypatch.setattr(graph_mod, "_graph", graph_mod.build_graph(InMemorySaver(), model))

    await store.init_db(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        trip_id = await service.new_trip()
        events = await collect(service.run_turn(trip_id, "Lisbon, May 1-2"))
        types = [e["type"] for e in events]
        assert "error" not in types, events
        text = "".join(e["delta"] for e in events if e["type"] == "text")
        assert text == "Planning Lisbon.All set."
        assert sum(t == "text" for t in types) > 2  # streamed in pieces
        starts = [e["name"] for e in events if e["type"] == "tool_start"]
        assert starts == ["update_trip", "search_places", "add_stop", "check_trip"]
        assert all(e["ok"] for e in events if e["type"] == "tool_end")
        assert "trip" in types
        assert events[-2] == {"type": "approval", "summary": "Lisbon, 2 days", "total_usd": 120.0}
        assert types[-1] == "done"

        thread = await service.get_thread(trip_id)
        assert thread["pending_approval"]["summary"] == "Lisbon, 2 days"
        assert thread["trip"]["status"] == "awaiting_approval"
        assert thread["messages"][0] == {"role": "user", "text": "Lisbon, May 1-2"}
        assert (await store.get_trip(trip_id))["status"] == "awaiting_approval"

        events = await collect(service.resume(trip_id, approved=True))
        assert [e["type"] for e in events if e["type"] != "text"] == ["trip", "done"]
        assert "".join(e["delta"] for e in events if e["type"] == "text") == (
            "Approved, enjoy Lisbon!"
        )
        thread = await service.get_thread(trip_id)
        trip = thread["trip"]
        assert trip["status"] == "approved"
        assert trip["days"][0]["stops"][0]["place"]["name"] == "MAAT"
        assert thread["pending_approval"] is None
        assert thread["messages"][-1]["text"] == "Approved, enjoy Lisbon!"
        assert (await store.get_trip(trip_id))["status"] == "approved"
    finally:
        await store.close_db()


async def test_errors_block_approval_and_new_message_declines(tmp_path, monkeypatch):
    from trip_planner.trip.models import Issue

    issues = [[Issue(code="missing_dates", severity="error", message="No dates")], []]
    monkeypatch.setattr(agent_tools, "check_trip", lambda trip: issues.pop(0))
    monkeypatch.setattr(agent_tools, "cost_breakdown", lambda trip: {"total": 0.0})
    model = ScriptedModel(messages=iter([
        ai("", ("request_approval", {"summary": "s"})),  # blocked by the error
        ai("Fixed.", ("request_approval", {"summary": "s"})),  # pauses
        ai("Okay, changing day 2."),  # after the user's new message
    ]))
    g = graph_mod.build_graph(InMemorySaver(), model)
    monkeypatch.setattr(graph_mod, "_graph", g)

    await store.init_db(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        trip_id = await service.new_trip()
        events = await collect(service.run_turn(trip_id, "book it"))
        assert [e["type"] for e in events][-2:] == ["approval", "done"]
        state = await g.aget_state({"configurable": {"thread_id": trip_id}})
        first_result = state.values["messages"][2]
        assert first_result.status == "error" and "No dates" in first_result.content

        events = await collect(service.run_turn(trip_id, "actually change day 2"))
        assert "approval" not in [e["type"] for e in events]
        thread = await service.get_thread(trip_id)
        assert thread["trip"]["status"] == "planning"
        assert thread["pending_approval"] is None
        state = await g.aget_state({"configurable": {"thread_id": trip_id}})
        assert "actually change day 2" in state.values["messages"][-2].content
    finally:
        await store.close_db()


async def test_searches_run_concurrently_and_merge(tmp_path, monkeypatch):
    import asyncio
    import time

    async def slow_search(query, near, max_results=8):
        await asyncio.sleep(0.3)  # like a scraper run
        return [Place(place_id=query, name=query.title(), lat=38.7, lng=-9.1)]

    monkeypatch.setattr(agent_tools.places, "search_places", slow_search)
    model = ScriptedModel(messages=iter([
        ai("",
           ("update_trip", {"destinations": ["Lisbon"], "start_date": "2026-05-01",
                            "end_date": "2026-05-01"}),
           ("search_places", {"query": "museum"}),
           ("search_places", {"query": "bakery"}),
           ("add_stop", {"date": "2026-05-01", "place_id": "bakery", "start": "09:00",
                         "duration_min": 30, "note": "pastries"})),
        ai("Done."),
    ]))
    monkeypatch.setattr(graph_mod, "_graph", graph_mod.build_graph(InMemorySaver(), model))

    await store.init_db(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        trip_id = await service.new_trip()
        t0 = time.monotonic()
        events = await collect(service.run_turn(trip_id, "Lisbon"))
        elapsed = time.monotonic() - t0
        ends = [(e["name"], e["ok"]) for e in events if e["type"] == "tool_end"]
        assert ends == [("update_trip", True), ("search_places", True),
                        ("search_places", True), ("add_stop", True)], events
        assert elapsed < 0.55  # two 0.3s searches overlapped instead of 0.6s in a row
        ms = {e["name"]: e["ms"] for e in events if e["type"] == "tool_end"}
        assert 280 <= ms["search_places"] < 550 and ms["add_stop"] < 100
        state = await graph_mod._graph.aget_state({"configurable": {"thread_id": trip_id}})
        assert set(state.values["places"]) == {"museum", "bakery"}  # both kept
        assert state.values["trip"]["days"][0]["stops"][0]["place"]["name"] == "Bakery"
    finally:
        await store.close_db()
