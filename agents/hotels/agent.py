from __future__ import annotations

import json
import time

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from agents.llm_factory import get_llm_for_agent
from agents.state import TravelState
from prompts.loader import get_prompt
from schemas.hotel import HotelSearchParams, HotelSearchResult
from tools.registry import ToolRegistry


async def hotels_node(state: TravelState) -> dict:
    """Hotels Agent — autonomous ReAct loop with retry strategies."""
    t0 = time.monotonic()
    agent_name = "hotels"

    llm = get_llm_for_agent(agent_name)
    tools = ToolRegistry.get_for_agent(agent_name)
    system_prompt = get_prompt(agent_name)

    constraints = state.get("constraints", {})
    destinations = constraints.get("destinations", [])
    city = destinations[0] if destinations else ""
    check_in = constraints.get("departure_date", "")
    check_out = constraints.get("return_date", "")
    num_travelers = constraints.get("num_travelers", 1)
    budget_usd = constraints.get("budget_usd")
    star_min = constraints.get("hotel_star_rating", 0) or 0
    cycle = state.get("gather_cycle_count", 0)

    fallback_params = HotelSearchParams(
        city_code=city or "Unknown",
        check_in=str(check_in or "2099-01-01"),
        check_out=str(check_out or "2099-01-02"),
        num_adults=num_travelers,
    )

    react_agent = create_react_agent(llm, tools, prompt=system_prompt)
    agent_result = await react_agent.ainvoke({
        "messages": [
            HumanMessage(
                content=(
                    f"Find hotels (autonomous — retry if empty):\n"
                    f"City: {city}\nCheck-in: {check_in}, Check-out: {check_out}\n"
                    f"Guests: {num_travelers}\n"
                    f"Budget: {'$' + str(budget_usd) if budget_usd else 'flexible'}\n"
                    f"Min stars: {star_min or 'no filter'}\nGather cycle: {cycle}\n\n"
                    "If no results: try alternate neighborhoods or adjust dates slightly."
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
        hotel_data = json.loads(raw_result) if raw_result else {}
        if isinstance(hotel_data, dict) and hotel_data.get("error"):
            errors.append({
                "agent": agent_name,
                "tool": "search_hotels_tool",
                "message": hotel_data["error"],
            })
            hotel_result = HotelSearchResult(params=fallback_params, options=[], source="error")
        elif hotel_data:
            hotel_result = HotelSearchResult.model_validate(hotel_data)
        else:
            hotel_result = HotelSearchResult(params=fallback_params, options=[])
    except Exception as exc:
        errors.append({"agent": agent_name, "message": f"Parse error: {exc}"})
        hotel_result = HotelSearchResult(params=fallback_params, options=[])

    duration_ms = round((time.monotonic() - t0) * 1000)
    timings = dict(state.get("agent_timings", {}))
    timings[agent_name] = duration_ms

    result: dict = {"hotel_results": hotel_result.model_dump(), "agent_timings": timings}
    if errors:
        result["errors"] = errors
    return result
