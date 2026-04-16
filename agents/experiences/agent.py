from __future__ import annotations

import json
import time

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from agents.llm_factory import get_llm_for_agent
from agents.state import TravelState
from prompts.loader import get_prompt
from tools.registry import ToolRegistry


async def experiences_node(state: TravelState) -> dict:
    """
    Experiences Agent: discovers restaurants, attractions, hidden gems, and activities.

    Uses create_react_agent to manage the multi-call tool loop automatically.
    The agent searches across all 4 categories; results are extracted directly
    from ToolMessages in the returned conversation history.
    """
    t0 = time.monotonic()
    agent_name = "experiences"

    llm = get_llm_for_agent(agent_name)
    tools = ToolRegistry.get_for_agent(agent_name)
    system_prompt = get_prompt(agent_name)

    constraints = state.get("constraints", {})
    destinations = constraints.get("destinations", [])
    city = destinations[0] if destinations else "the destination"
    activity_prefs = constraints.get("activity_preferences", [])
    dietary = constraints.get("dietary_restrictions", [])

    categories = ["restaurant", "attraction", "hidden_gem", "activity"]
    keywords = {
        "restaurant": f"best restaurants {', '.join(dietary) if dietary else ''}".strip(),
        "attraction": "must visit",
        "hidden_gem": "local secret off the beaten path",
        "activity": f"things to do {', '.join(activity_prefs) if activity_prefs else ''}".strip(),
    }

    # create_react_agent handles the multi-call tool loop automatically
    react_agent = create_react_agent(llm, tools, prompt=system_prompt)
    agent_result = await react_agent.ainvoke({
        "messages": [
            HumanMessage(
                content=(
                    f"Find experiences in {city}.\n"
                    f"Activity preferences: {activity_prefs}\n"
                    f"Dietary restrictions: {dietary}\n\n"
                    f"Search for ALL of these categories using search_places_tool: "
                    f"restaurant, attraction, hidden_gem, activity. "
                    f"Make a separate tool call for each category."
                )
            )
        ]
    })

    # Extract results directly from ToolMessages in the conversation history
    all_experiences: list[dict] = []
    for msg in agent_result.get("messages", []):
        if isinstance(msg, ToolMessage):
            try:
                raw = msg.content if isinstance(msg.content, str) else str(msg.content)
                items = json.loads(raw)
                if isinstance(items, list):
                    all_experiences.extend(items)
            except Exception:
                pass

    # Only backfill if we got ZERO results (complete API failure)
    if len(all_experiences) == 0:
        pass # Graceful degradation if no API results are found

    duration_ms = round((time.monotonic() - t0) * 1000)
    timings = dict(state.get("agent_timings", {}))
    timings[agent_name] = duration_ms

    return {
        "experience_results": all_experiences,
        "agent_timings": timings,
    }
