"""
Conditional edge routing functions for the AgenticTripPlanner LangGraph graph.

All functions receive the current TravelState and return either a node name
(str) or a list of Send() objects for fan-out.
"""

from __future__ import annotations

from langgraph.types import Send

from agents.state import TravelState

# ---------------------------------------------------------------------------
# Edge: supervisor → parallel fan-out
# ---------------------------------------------------------------------------

def route_after_supervisor(state: TravelState) -> list[Send]:
    """
    Fan-out from the supervisor to one or more parallel agents using Send().
    """
    targets: list[str] = state.get("parallel_targets") or [
        "research_node",
        "flights_node",
        "hotels_node",
        "experiences_node",
    ]
    node_names = [
        t if t.endswith("_node") else f"{t}_node"
        for t in targets
    ]
    return [Send(node_name, state) for node_name in node_names]


def route_after_coverage(state: TravelState) -> str | list[Send]:
    """
    Coverage node returns Command; this edge is a fallback when Command is not used.
    """
    targets = state.get("replenish_targets") or []
    if targets and state.get("gather_cycle_count", 0) < 3:
        return [Send(t if t.endswith("_node") else f"{t}_node", state) for t in targets]
    return "budget_node"


