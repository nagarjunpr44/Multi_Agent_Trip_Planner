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


# ---------------------------------------------------------------------------
# Edge: validator → itinerary (revision loop) or booking
# ---------------------------------------------------------------------------

MAX_REVISIONS = 2


def route_after_validator(state: TravelState) -> str:
    """
    If the itinerary failed validation and we haven't hit the revision cap,
    loop back to the itinerary node for a targeted re-planning pass.
    Budget data (flights, hotels, experiences) is unchanged — only the
    itinerary needs to be rebuilt using the validator's feedback.
    Otherwise proceed to booking.
    """
    validation_result = state.get("validation_result") or {}
    passed = validation_result.get("passed", False)
    revision_count = state.get("revision_count", 0)

    if not passed and revision_count < MAX_REVISIONS:
        return "itinerary_node"  # Re-plan itinerary using revision_feedback

    return "booking_node"
