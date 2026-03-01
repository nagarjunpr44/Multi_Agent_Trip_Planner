from __future__ import annotations

import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm_factory import get_llm_for_agent
from agents.state import TravelState
from prompts.loader import get_prompt
from schemas.agent_output import DestinationInfo
from tools.registry import ToolRegistry


async def research_node(state: TravelState) -> dict:
    """
    Research Agent: gathers destination intelligence using web search and weather tools.
    Returns a structured DestinationInfo.
    """
    t0 = time.monotonic()
    agent_name = "research"

    llm = get_llm_for_agent(agent_name)
    tools = ToolRegistry.get_for_agent(agent_name)
    llm_with_tools = llm.bind_tools(tools)
    structured_llm = llm.with_structured_output(DestinationInfo, method="function_calling")

    system_prompt = get_prompt(agent_name)
    constraints = state.get("constraints", {})
    destinations = constraints.get("destinations", [])
    dest_str = ", ".join(destinations) if destinations else "the destination"
    departure_date = constraints.get("departure_date", "")
    return_date = constraints.get("return_date", "")

    # Step 1: Let the LLM call research + weather tools
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=(
                f"Research destination: {dest_str}\n"
                f"Travel dates: {departure_date} to {return_date}\n"
                f"User query: {state['user_query']}\n\n"
                f"Use the web_research tool to get destination intel and "
                f"get_weather tool to get the weather forecast."
            )
        ),
    ]

    # Tool-calling loop (max 3 iterations)
    tool_results: list[str] = []
    current_messages = list(messages)
    for _ in range(3):
        response = await llm_with_tools.ainvoke(current_messages)
        if not response.tool_calls:
            break
        current_messages.append(response)
        from langchain_core.messages import ToolMessage
        for tc in response.tool_calls:
            tool_fn = ToolRegistry.get(tc["name"])
            result = await tool_fn.ainvoke(tc["args"])
            tool_results.append(str(result))
            current_messages.append(
                ToolMessage(content=str(result), tool_call_id=tc["id"])
            )

    # Step 2: Synthesize into structured output
    synthesis_messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=(
                f"Based on this research data, produce the DestinationInfo for {dest_str}.\n\n"
                f"Research data:\n" + "\n\n".join(tool_results[-4:])
            )
        ),
    ]
    destination_info: DestinationInfo = await structured_llm.ainvoke(synthesis_messages)

    duration_ms = round((time.monotonic() - t0) * 1000)
    timings = dict(state.get("agent_timings", {}))
    timings[agent_name] = duration_ms

    return {
        "destination_info": destination_info.model_dump(),
        "agent_timings": timings,
    }
