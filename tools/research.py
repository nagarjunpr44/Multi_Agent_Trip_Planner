from __future__ import annotations

import json
import os

from langchain_core.tools import tool

from config.settings import get_settings



@tool
async def web_research_tool(query: str, search_depth: str = "basic") -> str:
    """Search the web for up-to-date travel information.

    Args:
        query: Search query (e.g. "best time to visit Kyoto weather events 2026")
        search_depth: "basic" for quick search, "advanced" for deeper research

    Returns:
        JSON with search results and a synthesized summary
    """
    s = get_settings()
    if not s.apis.tavily_api_key:
        return json.dumps({"error": "TAVILY_API_KEY is not configured. Cannot perform web research."})

    # Use the official langchain-tavily integration — built for agent tool loops
    os.environ["TAVILY_API_KEY"] = s.apis.tavily_api_key
    from langchain_tavily import TavilySearch

    depth = "advanced" if search_depth == "advanced" else "basic"
    max_results = 7 if depth == "advanced" else 5
    search_tool = TavilySearch(
        max_results=max_results,
        search_depth=depth,
        topic="general",
    )
    raw = search_tool.invoke({"query": query})

    # langchain-tavily returns a dict with results list and optional answer
    if isinstance(raw, dict):
        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "score": r.get("score", 0.0),
            }
            for r in raw.get("results", [])
        ]
        return json.dumps({
            "query": query,
            "results": results,
            "summary": raw.get("answer", ""),
            "follow_up_questions": raw.get("follow_up_questions", []),
            "is_mock": False,
        })

    # Fallback: raw is a plain string (older versions return str)
    return json.dumps({
        "query": query,
        "results": [],
        "summary": str(raw),
        "is_mock": False,
    })
