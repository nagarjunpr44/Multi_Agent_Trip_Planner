from __future__ import annotations

"""
Conditional edge routing functions for the AgenticTripPlanner LangGraph graph.

All functions receive the current TravelState and return either a node name
(str) or a list of Send() objects for fan-out.
"""

from langgraph.types import Send

from agents.state import TravelState

# ---------------------------------------------------------------------------
# Edge: supervisor → parallel fan-out
# ---------------------------------------------------------------------------

def route_after_supervisor(state: TravelState) -> list[Send]:
    """
    Fan-out from the supervisor to one or more parallel agents using Send().

    The supervisor populates `parallel_targets` with agent names such as:
      ["research", "flights", "hotels", "experiences"]

    Each Send() delivers the same TravelState snapshot to its target node.
    If parallel_targets is missing, fall back to all four agents.
    """
    targets: list[str] = state.get("parallel_targets") or [
        "research_node",
        "flights_node",
        "hotels_node",
        "experiences_node",
    ]
    # Ensure target names have _node suffix (graph node names)
    node_names = [
        t if t.endswith("_node") else f"{t}_node"
        for t in targets
    ]
    return [Send(node_name, state) for node_name in node_names]



