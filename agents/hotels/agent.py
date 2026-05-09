from __future__ import annotations

import json
import time

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from agents.llm_factory import get_llm_for_agent
from agents.state import TravelState
from prompts.loader import get_prompt
from schemas.hotel import HotelSearchParams, HotelSearchResult
from tools.registry import ToolRegistry


async def hotels_node(state: TravelState) -> dict:
    """Hotels Agent: searches for accommodations via SerpApi Google Hotels."""
    t0 = time.monotonic()
    agent_name = "hotels"

    llm = get_llm_for_agent(agent_name)
    tools = ToolRegistry.get_for_agent(agent_name)
    llm_with_tools = llm.bind_tools(tools)

    system_prompt = get_prompt(agent_name)
    constraints = state.get("constraints", {})
    destinations = constraints.get("destinations", [])
    city = destinations[0] if destinations else ""
    check_in = constraints.get("departure_date", "")
    check_out = constraints.get("return_date", "")
    num_travelers = constraints.get("num_travelers", 1)
    budget_usd = constraints.get("budget_usd")
    star_min = constraints.get("hotel_star_rating", 0) or 0
    fallback_params = HotelSearchParams(
        city_code=city or "Unknown",
        check_in=str(check_in or "2099-01-01"),
        check_out=str(check_out or "2099-01-02"),
        num_adults=num_travelers,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=(
                f"Search for hotels:\n"
                f"City: {city}\n"
                f"Check-in: {check_in}, Check-out: {check_out}\n"
                f"Guests: {num_travelers}\n"
                f"Budget: {'$' + str(budget_usd) if budget_usd else 'flexible'}\n"
                f"Min stars: {star_min or 'no filter'}\n"
                f"Use the search_hotels tool. Infer IATA city code from city name."
            )
        ),
    ]

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
            current_messages.append(ToolMessage(content=raw_result, tool_call_id=tc["id"]))
        break

    errors: list[dict] = []
    try:
        hotel_data = json.loads(raw_result)
        if isinstance(hotel_data, dict) and hotel_data.get("error"):
            errors.append(
                {
                    "agent": agent_name,
                    "tool": "search_hotels_tool",
                    "message": hotel_data["error"],
                    "source": hotel_data.get("source", "unknown"),
                }
            )
            hotel_result = HotelSearchResult(
                params=fallback_params,
                options=[],
                source=hotel_data.get("source", "error"),
            )
        else:
            hotel_result = HotelSearchResult.model_validate(hotel_data)
    except Exception as exc:
        errors.append(
            {
                "agent": agent_name,
                "tool": "search_hotels_tool",
                "message": f"Could not parse hotel search result: {exc}",
            }
        )
        hotel_result = HotelSearchResult(params=fallback_params, options=[])

    duration_ms = round((time.monotonic() - t0) * 1000)
    timings = dict(state.get("agent_timings", {}))
    timings[agent_name] = duration_ms

    result = {
        "hotel_results": hotel_result.model_dump(),
        "agent_timings": timings,
    }
    if errors:
        result["errors"] = errors
    return result
