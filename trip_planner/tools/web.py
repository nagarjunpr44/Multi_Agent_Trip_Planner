"""Web search via Tavily."""

from __future__ import annotations


async def web_search(query: str, max_results: int = 5) -> list[dict]:
    """[{"title", "url", "content"}], content trimmed to ~500 chars."""
    raise NotImplementedError
