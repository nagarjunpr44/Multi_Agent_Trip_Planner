from agents.graph import get_graph_sync
from tools.registry import ToolRegistry, initialize_registry


def test_tool_registry_initializes_expected_tools() -> None:
    initialize_registry()

    assert {
        "search_flights_tool",
        "search_hotels_tool",
        "web_research_tool",
        "get_weather_tool",
        "search_places_tool",
        "get_travel_distance_tool",
    }.issubset(set(ToolRegistry.list_all()))


def test_graph_compiles_with_memory_saver() -> None:
    initialize_registry()
    graph = get_graph_sync()

    assert type(graph).__name__ == "CompiledStateGraph"
