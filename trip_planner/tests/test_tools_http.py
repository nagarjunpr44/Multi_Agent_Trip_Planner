import httpx
import pytest

from trip_planner import store
from trip_planner.config import get_settings
from trip_planner.tools import ToolError, http
from trip_planner.tools.cache import cached


def mock_http(monkeypatch, handler) -> list[httpx.Request]:
    """Route every tool HTTP call to `handler(request) -> httpx.Response`; returns the calls."""
    calls: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)

    monkeypatch.setattr(http, "client", lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(record)
    ))
    return calls


def set_key(monkeypatch, name: str, value: str) -> None:
    monkeypatch.setattr(get_settings(), name, value)


async def test_request_errors_are_tool_errors(monkeypatch):
    mock_http(monkeypatch, lambda r: httpx.Response(403, json={"error": {"message": "bad key"}}))
    with pytest.raises(ToolError, match="X error 403: bad key"):
        await http.request("X", "GET", "https://example.com")

    def boom(r):
        raise httpx.ConnectTimeout("slow")

    mock_http(monkeypatch, boom)
    with pytest.raises(ToolError, match="X request failed: ConnectTimeout"):
        await http.request("X", "GET", "https://example.com")


async def test_serpapi_error_payload(monkeypatch):
    set_key(monkeypatch, "serpapi_api_key", "k")
    mock_http(monkeypatch, lambda r: httpx.Response(200, json={"error": "Invalid date"}))
    with pytest.raises(ToolError, match="Invalid date"):
        await http.serpapi({})
    no_results = {"error": "Google hasn't returned any results for this query."}
    mock_http(monkeypatch, lambda r: httpx.Response(200, json=no_results))
    assert await http.serpapi({}) == no_results


async def test_cached(tmp_path):
    calls = []

    async def fetch():
        calls.append(1)
        return [{"a": 1}]

    assert await cached("ns", {"x": 1}, fetch) == [{"a": 1}]  # no DB: always fetches
    await store.init_db(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    try:
        await cached("ns", {"x": 1}, fetch)
        assert await cached("ns", {"x": 1}, fetch) == [{"a": 1}]
        await cached("ns", {"x": 2}, fetch)
        assert len(calls) == 3
    finally:
        await store.close_db()
