from __future__ import annotations

import json
import time

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from agents.llm_factory import get_llm_for_agent
from agents.state import TravelState
from prompts.loader import get_prompt
from schemas.itinerary import Experience
from tools.registry import ToolRegistry


async def experiences_node(state: TravelState) -> dict:
    """
    Experiences Agent: discovers restaurants, attractions, hidden gems, and activities
    using Google Places.
    """
    t0 = time.monotonic()
    agent_name = "experiences"

    llm = get_llm_for_agent(agent_name)
    tools = ToolRegistry.get_for_agent(agent_name)
    llm_with_tools = llm.bind_tools(tools)

    system_prompt = get_prompt(agent_name)
    constraints = state.get("constraints", {})
    destinations = constraints.get("destinations", [])
    city = destinations[0] if destinations else "the destination"
    activity_prefs = constraints.get("activity_preferences", [])
    dietary = constraints.get("dietary_restrictions", [])

    # Search 4 categories in sequence (tool calls)
    categories = ["restaurant", "attraction", "hidden_gem", "activity"]
    keywords = {
        "restaurant": f"best restaurants {', '.join(dietary) if dietary else ''}".strip(),
        "attraction": "must visit",
        "hidden_gem": "local secret off the beaten path",
        "activity": f"things to do {', '.join(activity_prefs) if activity_prefs else ''}".strip(),
    }

    all_experiences: list[dict] = []
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=(
                f"Find experiences in {city}.\n"
                f"Activity preferences: {activity_prefs}\n"
                f"Dietary restrictions: {dietary}\n\n"
                f"Use search_places_tool for each of these categories: "
                f"restaurant, attraction, hidden_gem, activity."
            )
        ),
    ]

    current_messages = list(messages)
    for _ in range(8):  # allow multiple tool calls
        response = await llm_with_tools.ainvoke(current_messages)
        if not response.tool_calls:
            break
        current_messages.append(response)
        for tc in response.tool_calls:
            tool_fn = ToolRegistry.get(tc["name"])
            result = await tool_fn.ainvoke(tc["args"])
            try:
                items = json.loads(str(result))
                if isinstance(items, list):
                    all_experiences.extend(items)
            except Exception:
                pass
            current_messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

    # If the LLM didn't call all 4 categories, fill with mocks
    if len(all_experiences) < 8:
        from tools.places import _mock_places
        for cat in categories:
            if not any(e.get("category") == cat for e in all_experiences):
                all_experiences.extend(_mock_places(city, cat, keywords[cat]))

    duration_ms = round((time.monotonic() - t0) * 1000)
    timings = dict(state.get("agent_timings", {}))
    timings[agent_name] = duration_ms

    return {
        "experience_results": all_experiences,
        "agent_timings": timings,
    }
