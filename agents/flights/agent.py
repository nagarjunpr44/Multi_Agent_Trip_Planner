from __future__ import annotations

import json
import time

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from agents.llm_factory import get_llm_for_agent
from agents.state import TravelState
from prompts.loader import get_prompt
from schemas.flight import FlightSearchParams, FlightSearchResult
from tools.registry import ToolRegistry


async def flights_node(state: TravelState) -> dict:
    """
    Flights Agent — autonomous ReAct loop: retries with alternate airports/dates if empty.
    """
    t0 = time.monotonic()
    agent_name = "flights"

    llm = get_llm_for_agent(agent_name)
    tools = ToolRegistry.get_for_agent(agent_name)
    system_prompt = get_prompt(agent_name)

    constraints = state.get("constraints", {})
    origin = constraints.get("origin_city", "")
    destinations = constraints.get("destinations", [])
    dest = destinations[0] if destinations else ""
    departure_date = constraints.get("departure_date", "")
    return_date = constraints.get("return_date", "")
    num_travelers = constraints.get("num_travelers", 1)
    cycle = state.get("gather_cycle_count", 0)

    fallback_params = FlightSearchParams(
        origin=(origin[:3] or "UNK").upper(),
        destination=(dest[:3] or "UNK").upper(),
        departure_date=str(departure_date or "2099-01-01"),
        return_date=str(return_date) if return_date else None,
        num_adults=num_travelers,
    )

    react_agent = create_react_agent(llm, tools, prompt=system_prompt)
    agent_result = await react_agent.ainvoke({
        "messages": [
            HumanMessage(
                content=(
                    f"Find flights (autonomous — retry until you get options or exhaust strategies):\n"
                    f"Origin: {origin}\nDestination: {dest}\n"
                    f"Departure: {departure_date}\nReturn: {return_date}\n"
                    f"Travelers: {num_travelers}\nGather cycle: {cycle}\n\n"
                    "If no results: try nearby airports, ±1 day shift, or different IATA codes.\n"
                    "Call search_flights_tool at least once."
                )
            )
        ]
    })

    raw_result = ""
    for msg in agent_result.get("messages", []):
        if isinstance(msg, ToolMessage) and msg.content:
            raw_result = str(msg.content)

    errors: list[dict] = []
    try:
        flight_data = json.loads(raw_result) if raw_result else {}
        if isinstance(flight_data, dict) and flight_data.get("error"):
            errors.append({
                "agent": agent_name,
                "tool": "search_flights_tool",
                "message": flight_data["error"],
            })
            flight_result = FlightSearchResult(
                params=fallback_params, options=[], source="error"
            )
        elif flight_data:
            flight_result = FlightSearchResult.model_validate(flight_data)
        else:
            flight_result = FlightSearchResult(params=fallback_params, options=[])
    except Exception as exc:
        errors.append({
            "agent": agent_name,
            "message": f"Could not parse flight search result: {exc}",
        })
        flight_result = FlightSearchResult(params=fallback_params, options=[])

    duration_ms = round((time.monotonic() - t0) * 1000)
    timings = dict(state.get("agent_timings", {}))
    timings[agent_name] = duration_ms

    result: dict = {
        "flight_results": flight_result.model_dump(),
        "agent_timings": timings,
    }
    if errors:
        result["errors"] = errors
    return result
