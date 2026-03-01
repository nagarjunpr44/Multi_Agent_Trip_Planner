from __future__ import annotations

import json
import time

from langchain_core.messages import HumanMessage, ToolMessage, SystemMessage

from agents.llm_factory import get_llm_for_agent
from agents.state import TravelState
from prompts.loader import get_prompt
from schemas.flight import FlightSearchResult
from tools.registry import ToolRegistry


async def flights_node(state: TravelState) -> dict:
    """
    Flights Agent: searches for flight options using the Amadeus tool.
    Returns a structured FlightSearchResult.
    """
    t0 = time.monotonic()
    agent_name = "flights"

    llm = get_llm_for_agent(agent_name)
    tools = ToolRegistry.get_for_agent(agent_name)
    llm_with_tools = llm.bind_tools(tools)

    system_prompt = get_prompt(agent_name)
    constraints = state.get("constraints", {})
    origin = constraints.get("origin_city", "")
    destinations = constraints.get("destinations", [])
    dest = destinations[0] if destinations else ""
    departure_date = constraints.get("departure_date", "")
    return_date = constraints.get("return_date", "")
    num_travelers = constraints.get("num_travelers", 1)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=(
                f"Search for flights:\n"
                f"Origin: {origin}\n"
                f"Destination: {dest}\n"
                f"Departure: {departure_date}\n"
                f"Return: {return_date}\n"
                f"Travelers: {num_travelers}\n"
                f"User query: {state['user_query']}\n\n"
                f"Use the search_flights tool. Infer IATA codes from city names."
            )
        ),
    ]

    # Tool-calling loop
    raw_result: str = ""
    current_messages = list(messages)
    for _ in range(3):
        response = await llm_with_tools.ainvoke(current_messages)
        if not response.tool_calls:
            break
        current_messages.append(response)
        for tc in response.tool_calls:
            tool_fn = ToolRegistry.get(tc["name"])
            result = await tool_fn.ainvoke(tc["args"])
            raw_result = str(result)
            current_messages.append(
                ToolMessage(content=raw_result, tool_call_id=tc["id"])
            )
        break  # Only need one flight search call

    # Parse the tool result into FlightSearchResult
    try:
        flight_data = json.loads(raw_result)
        flight_result = FlightSearchResult.model_validate(flight_data)
    except Exception:
        from schemas.flight import FlightSearchParams
        params = FlightSearchParams(
            origin=origin[:3].upper() or "JFK",
            destination=dest[:3].upper() or "NRT",
            departure_date=departure_date or "2026-06-01",
        )
        from tools.flights import _mock_flights
        flight_result = _mock_flights(params)

    duration_ms = round((time.monotonic() - t0) * 1000)
    timings = dict(state.get("agent_timings", {}))
    timings[agent_name] = duration_ms

    return {
        "flight_results": flight_result.model_dump(),
        "agent_timings": timings,
    }
