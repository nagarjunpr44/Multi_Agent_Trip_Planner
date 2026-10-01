"""The one place tools make HTTP calls. Tests monkeypatch `client`."""

from __future__ import annotations

from typing import Any

import httpx

from trip_planner.config import get_settings
from trip_planner.tools import ToolError


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=get_settings().tool_timeout_seconds)


def require_key(key: str, name: str) -> str:
    if not key:
        raise ToolError(f"{name} is not configured")
    return key


async def request(api: str, method: str, url: str, **kwargs: Any) -> Any:
    """Send one request and return the JSON body. Any failure becomes a short ToolError."""
    try:
        async with client() as c:
            resp = await c.request(method, url, **kwargs)
    except httpx.HTTPError as e:
        raise ToolError(f"{api} request failed: {type(e).__name__}") from e
    if resp.status_code >= 400:
        raise ToolError(f"{api} error {resp.status_code}: {_error_text(resp)}")
    try:
        return resp.json()
    except ValueError as e:
        raise ToolError(f"{api} returned invalid JSON") from e


def _error_text(resp: httpx.Response) -> str:
    try:
        err = resp.json()
    except ValueError:
        return resp.text[:200]
    # Google: {"error": {"message"}}, SerpApi: {"error"}, Tavily: {"detail": {"error"}}
    while isinstance(err, dict):
        key = next((k for k in ("error", "detail", "message") if k in err), None)
        if key is None:
            break
        err = err[key]
    return str(err)[:200]


async def serpapi(params: dict) -> dict:
    """SerpApi search. It reports some errors (and "no results") with HTTP 200 + "error"."""
    key = require_key(get_settings().serpapi_api_key, "SERPAPI_API_KEY")
    params = {**params, "api_key": key}
    data = await request("SerpApi", "GET", "https://serpapi.com/search", params=params)
    error = data.get("error")
    if error and "hasn't returned any results" not in error:
        raise ToolError(f"SerpApi error: {str(error)[:200]}")
    return data
