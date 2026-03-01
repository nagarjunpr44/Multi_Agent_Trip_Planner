from __future__ import annotations

import json

from langchain_core.tools import tool

from config.settings import get_settings


def _mock_research(query: str) -> dict:
    return {
        "query": query,
        "results": [
            {
                "title": f"Comprehensive Guide: {query}",
                "url": "https://example.com/travel-guide",
                "content": f"Detailed information about {query}. This destination offers rich cultural experiences, excellent cuisine, and diverse landscapes. Best visited during spring and autumn. Visa requirements vary by nationality.",
                "score": 0.95,
            },
            {
                "title": f"Travel Tips for {query}",
                "url": "https://example.com/tips",
                "content": f"Top tips for visiting {query}: Book accommodation early during peak season, use public transport, try local street food, and respect cultural customs.",
                "score": 0.88,
            },
        ],
        "summary": f"Research results for: {query}. Multiple sources confirm this is a popular and recommended destination.",
        "is_mock": True,
    }


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
    if s.app.mock_fallback or not s.apis.tavily_api_key:
        return json.dumps(_mock_research(query))

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=s.apis.tavily_api_key)

        if search_depth == "advanced":
            # Use Tavily's Research API for deep research
            response = client.search(
                query=query,
                search_depth="advanced",
                max_results=7,
                include_answer=True,
            )
        else:
            response = client.search(
                query=query,
                search_depth="basic",
                max_results=5,
                include_answer=True,
            )

        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "score": r.get("score", 0.0),
            }
            for r in response.get("results", [])
        ]

        return json.dumps({
            "query": query,
            "results": results,
            "summary": response.get("answer", ""),
            "is_mock": False,
        })
    except Exception as exc:
        result = _mock_research(query)
        result["error"] = str(exc)
        return json.dumps(result)
