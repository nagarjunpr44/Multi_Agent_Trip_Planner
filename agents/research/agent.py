from __future__ import annotations

import time

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from agents.llm_factory import get_llm_for_agent
from agents.state import TravelState
from prompts.loader import get_prompt
from schemas.agent_output import DestinationInfo
from tools.mcp_client import get_mcp_tools
from tools.registry import ToolRegistry


async def research_node(state: TravelState) -> dict:
    """
    Research Agent: gathers destination intelligence using web search and weather tools.

    Uses create_react_agent to handle the tool-calling loop automatically, then
    does a separate structured-output synthesis pass over the collected tool results.
    """
    t0 = time.monotonic()
    agent_name = "research"

    llm = get_llm_for_agent(agent_name)
    tools = ToolRegistry.get_for_agent(agent_name)
    mcp_tools = await get_mcp_tools()
    if mcp_tools:
        tools = tools + mcp_tools
    system_prompt = get_prompt(agent_name)

    constraints = state.get("constraints", {})
    destinations = constraints.get("destinations", [])
    dest_str = ", ".join(destinations) if destinations else "the destination"
    departure_date = constraints.get("departure_date", "")
    return_date = constraints.get("return_date", "")

    # Step 1: ReAct agent handles tool-calling loop automatically
    react_agent = create_react_agent(llm, tools, prompt=system_prompt)
    agent_result = await react_agent.ainvoke({
        "messages": [
            HumanMessage(
                content=(
                    f"Research destination: {dest_str}\n"
                    f"Travel dates: {departure_date} to {return_date}\n"
                    f"User query: {state['user_query']}\n\n"
                    f"Use ALL available tools:\n"
                    f"- web_research_tool: get destination intel, travel tips, local insights\n"
                    f"- get_weather_tool: weather forecast for the travel dates\n"
                    f"- search_tripadvisor_tool: destination ratings, top attractions, "
                    f"traveler reviews (call with category='geos' for overview, "
                    f"then category='attractions' for top sights)"
                )
            )
        ]
    })

    # Extract all tool results from the ReAct conversation
    tool_results: list[str] = [
        str(m.content)
        for m in agent_result.get("messages", [])
        if isinstance(m, ToolMessage)
    ]

    # Step 2: Synthesize tool results into a structured DestinationInfo
    structured_llm = llm.with_structured_output(DestinationInfo, method="function_calling")
    synthesis_messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=(
                f"Based on this research data (web search, weather, TripAdvisor), "
                f"produce the DestinationInfo for {dest_str}.\n\n"
                "Research data:\n" + "\n\n".join(tool_results[-6:])
                if tool_results
                else (
                    "No tool data was retrieved. Produce a best-effort "
                    f"DestinationInfo for {dest_str}."
                )
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
