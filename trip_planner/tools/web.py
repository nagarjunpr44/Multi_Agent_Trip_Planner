"""Web search via Tavily."""

from __future__ import annotations

from trip_planner.config import get_settings
from trip_planner.tools import http
from trip_planner.tools.cache import cached


async def web_search(query: str, max_results: int = 5) -> list[dict]:
    """[{"title", "url", "content"}], content trimmed to ~500 chars."""
    body = {"query": query, "max_results": max_results, "search_depth": "basic"}

    async def fetch() -> list[dict]:
        key = http.require_key(get_settings().tavily_api_key, "TAVILY_API_KEY")
        data = await http.request(
            "Tavily",
            "POST",
            "https://api.tavily.com/search",
            json=body,
            headers={"Authorization": f"Bearer {key}"},
        )
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": _trim(r.get("content", "")),
            }
            for r in data.get("results", [])
        ]

    return await cached("web", body, fetch, ttl_hours=24)


def _trim(text: str, limit: int = 500) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"
