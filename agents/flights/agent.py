from __future__ import annotations

import json
import time

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from agents.llm_factory import get_llm_for_agent
from agents.state import TravelState
from prompts.loader import get_prompt
from schemas.flight import FlightSearchParams, FlightSearchResult
from tools.registry import ToolRegistry


async def flights_node(state: TravelState) -> dict:
    """
    Flights Agent: searches for flight options using the SerpApi Google Flights tool.
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
    fallback_params = FlightSearchParams(
        origin=(origin[:3] or "UNK").upper(),
        destination=(dest[:3] or "UNK").upper(),
        departure_date=str(departure_date or "2099-01-01"),
        return_date=str(return_date) if return_date else None,
        num_adults=num_travelers,
    )

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
    errors: list[dict] = []
    try:
        flight_data = json.loads(raw_result)
        if isinstance(flight_data, dict) and flight_data.get("error"):
            errors.append(
                {
                    "agent": agent_name,
                    "tool": "search_flights_tool",
                    "message": flight_data["error"],
                    "source": flight_data.get("source", "unknown"),
                }
            )
            flight_result = FlightSearchResult(
                params=fallback_params,
                options=[],
                source=flight_data.get("source", "error"),
            )
        else:
            flight_result = FlightSearchResult.model_validate(flight_data)
    except Exception as exc:
        errors.append(
            {
                "agent": agent_name,
                "tool": "search_flights_tool",
                "message": f"Could not parse flight search result: {exc}",
            }
        )
        flight_result = FlightSearchResult(params=fallback_params, options=[])

    duration_ms = round((time.monotonic() - t0) * 1000)
    timings = dict(state.get("agent_timings", {}))
    timings[agent_name] = duration_ms

    result = {
        "flight_results": flight_result.model_dump(),
        "agent_timings": timings,
    }
    if errors:
        result["errors"] = errors
    return result
