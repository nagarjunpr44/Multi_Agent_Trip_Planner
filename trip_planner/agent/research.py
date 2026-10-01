"""Research sub-agent: a cheap model reads search results and returns a short brief,
so raw results never enter the planner's context."""

from __future__ import annotations

import json

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from trip_planner.llm import get_llm
from trip_planner.tools import ToolError, places, web

SYSTEM_PROMPT = """\
You research one city for a travel planner. Use web_search and search_places, then reply \
with a brief of at most 300 words: neighborhoods worth building a day around, must-sees, \
and specific named places that match the focus (give each place's place_id when it came \
from search_places), plus practical tips (transport, reservations, closures). \
Plain text, no preamble. Never invent places, prices or opening hours."""


async def research_city(city: str, focus: str) -> tuple[str, dict[str, dict]]:
    """Returns (brief, places found via search_places keyed by place_id)."""
    found: dict[str, dict] = {}

    @tool("web_search")
    async def web_search_tool(query: str) -> str:
        """Search the web. Returns titles, urls and snippets."""
        try:
            return json.dumps(await web.web_search(query))
        except ToolError as e:
            return f"Error: {e}"

    @tool("search_places")
    async def search_places_tool(queries: list[str]) -> str:
        """Find real places in the city. Pass all queries at once (one slow call), e.g.
        ["wine bars", "historic sights"]. Returns place_id, name, rating."""
        try:
            results = await places.search_many(queries, city, max_results=5)
        except ToolError as e:
            return f"Error: {e}"
        for p in results:
            found[p.place_id] = p.model_dump(mode="json")
        return json.dumps(
            [{"place_id": p.place_id, "name": p.name, "rating": p.rating, "address": p.address}
             for p in results]
        )

    agent = create_agent(
        get_llm("research"), [web_search_tool, search_places_tool], system_prompt=SYSTEM_PROMPT
    )
    result = await agent.ainvoke(
        {"messages": [HumanMessage(f"City: {city}\nFocus: {focus}")]}, {"recursion_limit": 20}
    )
    return result["messages"][-1].text, found
