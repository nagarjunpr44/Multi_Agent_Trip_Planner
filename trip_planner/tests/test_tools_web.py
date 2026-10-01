import json

import httpx
import pytest

from trip_planner import store
from trip_planner.tests.test_tools_http import mock_http, set_key
from trip_planner.tools import ToolError
from trip_planner.tools.web import web_search

LONG = "Lisbon's trams climb steep hills. " * 40
PAYLOAD = {
    "query": "lisbon tram 28 tips",
    "results": [
        {"title": "Tram 28 guide", "url": "https://example.com/28", "content": LONG,
         "score": 0.93, "raw_content": None},
        {"title": "Short", "url": "https://example.com/s", "content": "Go early.\n Avoid noon.",
         "score": 0.5},
    ],
    "response_time": 1.2,
}


async def test_web_search(monkeypatch):
    set_key(monkeypatch, "tavily_api_key", "tk")
    calls = mock_http(monkeypatch, lambda r: httpx.Response(200, json=PAYLOAD))
    long, short = await web_search("lisbon tram 28 tips", max_results=2)

    assert json.loads(calls[0].content) == {
        "query": "lisbon tram 28 tips", "max_results": 2, "search_depth": "basic"
    }
    assert calls[0].headers["Authorization"] == "Bearer tk"
    assert set(long) == {"title", "url", "content"}
    assert len(long["content"]) <= 501 and long["content"].endswith("…")
    assert LONG.startswith(long["content"][:-1])
    assert short == {"title": "Short", "url": "https://example.com/s",
                     "content": "Go early. Avoid noon."}


async def test_web_search_errors_and_cache(monkeypatch, tmp_path):
    set_key(monkeypatch, "tavily_api_key", "")
    with pytest.raises(ToolError, match="TAVILY_API_KEY is not configured"):
        await web_search("x")
    set_key(monkeypatch, "tavily_api_key", "tk")
    mock_http(monkeypatch, lambda r: httpx.Response(401, json={
        "detail": {"error": "Unauthorized: missing or invalid API key."}
    }))
    with pytest.raises(ToolError, match="401: Unauthorized"):
        await web_search("x")

    calls = mock_http(monkeypatch, lambda r: httpx.Response(200, json=PAYLOAD))
    await store.init_db(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        assert await web_search("x") == await web_search("x")
    finally:
        await store.close_db()
    assert len(calls) == 1
