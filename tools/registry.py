from __future__ import annotations

from langchain_core.tools import BaseTool


class ToolRegistry:
    """Central registry mapping tool names to LangChain tool callables."""

    _registry: dict[str, BaseTool] = {}

    # Maps agent name → list of tool names it should receive
    _agent_tools: dict[str, list[str]] = {
        "supervisor": [],
        "research": ["web_research_tool", "get_weather_tool", "search_tripadvisor_tool"],
        "flights": ["search_flights_tool"],
        "hotels": ["search_hotels_tool"],
        "experiences": ["search_places_tool"],
        "budget": ["convert_currency_tool"],
        "itinerary": ["get_travel_distance_tool"],
        "validator": [],
        "booking": ["search_flights_tool", "search_hotels_tool"],
        "memory": [],
    }

    @classmethod
    def register(cls, name: str, tool_fn: BaseTool) -> None:
        cls._registry[name] = tool_fn

    @classmethod
    def get(cls, name: str) -> BaseTool:
        if name not in cls._registry:
            raise KeyError(f"Tool '{name}' not registered. Known: {list(cls._registry)}")
        return cls._registry[name]

    @classmethod
    def get_for_agent(cls, agent_name: str) -> list[BaseTool]:
        """Return all tools assigned to a given agent."""
        tool_names = cls._agent_tools.get(agent_name, [])
        return [cls._registry[n] for n in tool_names if n in cls._registry]

    @classmethod
    def list_all(cls) -> list[str]:
        return list(cls._registry.keys())


def initialize_registry() -> None:
    """Register all tools at startup. Called from FastAPI lifespan."""
    from tools.currency import convert_currency_tool
    from tools.flights import search_flights_tool
    from tools.hotels import search_hotels_tool
    from tools.maps import get_travel_distance_tool
    from tools.places import search_places_tool
    from tools.research import web_research_tool
    from tools.tripadvisor import search_tripadvisor_tool
    from tools.weather import get_weather_tool

    for tool_fn in [
        search_flights_tool,
        search_hotels_tool,
        get_weather_tool,
        search_places_tool,
        web_research_tool,
        convert_currency_tool,
        get_travel_distance_tool,
        search_tripadvisor_tool,
    ]:
        # Register by the tool's actual .name (what the LLM uses in tool calls)
        ToolRegistry.register(tool_fn.name, tool_fn)
