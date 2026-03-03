"""
Optional MCP server integration for AgenticTripPlanner.

When MCP_ENABLED=true and the required API keys are set, this module
spins up MCP server subprocesses and returns their tools as LangChain
BaseTool objects compatible with create_react_agent and ToolNode.

Configured servers:
  - tripadvisor: @tripadvisor/tripadvisor-mcp
      Provides: location search, reviews, photos, nearby attractions
      Requires: TRIPADVISOR_API_KEY + Node.js (npx)

Usage in agents:
    from tools.mcp_client import get_mcp_tools
    mcp_tools = await get_mcp_tools()
    all_tools = native_tools + mcp_tools

If MCP_ENABLED=false, Node.js is unavailable, or the server fails to start,
get_mcp_tools() returns [] so the system works without MCP.
"""

from __future__ import annotations

import logging
import os

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


async def get_mcp_tools() -> list[BaseTool]:
    """
    Return LangChain-compatible tools from configured MCP servers.

    Returns an empty list if:
      - MCP_ENABLED is false (default)
      - Required API keys are missing
      - Node.js / npx is not available on PATH
      - Any MCP server fails to start
    """
    from config.settings import get_settings

    s = get_settings()

    if not s.app.mcp_enabled:
        return []

    servers: dict = {}

    # TripAdvisor MCP server
    tripadvisor_key = s.apis.tripadvisor_api_key
    if tripadvisor_key:
        servers["tripadvisor"] = {
            "command": "npx",
            "args": ["-y", "@tripadvisor/tripadvisor-mcp"],
            "transport": "stdio",
            "env": {
                **os.environ,
                "TRIPADVISOR_API_KEY": tripadvisor_key,
            },
        }
        logger.info("MCP: TripAdvisor server configured")
    else:
        logger.warning("MCP: TRIPADVISOR_API_KEY not set — TripAdvisor MCP server skipped")

    if not servers:
        logger.warning("MCP: no servers configured — returning empty tool list")
        return []

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient  # type: ignore[import]

        async with MultiServerMCPClient(servers) as client:
            tools = client.get_tools()
            logger.info("MCP: loaded %d tools from %d server(s)", len(tools), len(servers))
            return tools  # type: ignore[return-value]

    except ImportError:
        logger.warning(
            "MCP: langchain-mcp-adapters not installed — "
            "run 'uv add langchain-mcp-adapters' to enable MCP support"
        )
        return []
    except FileNotFoundError:
        logger.warning(
            "MCP: npx not found — install Node.js to use MCP servers. "
            "Continuing without MCP tools."
        )
        return []
    except Exception as exc:
        logger.error("MCP: server startup failed (%s) — continuing without MCP tools", exc)
        return []
