from __future__ import annotations

import operator
from typing import Annotated, Any, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph import MessagesState
from typing_extensions import TypedDict


def _merge_dicts(a: dict, b: dict) -> dict:
    """Merge reducer for dict-typed state fields updated by parallel nodes."""
    return {**a, **b}



class TravelState(MessagesState):
    # ── Input ───────────────────────────────────────────────────────────────
    session_id: str
    user_query: str
    constraints: dict[str, Any]  # serialized TripConstraints
    mode: Literal["autonomous", "hitl"]

    # ── Supervisor plan ──────────────────────────────────────────────────────
    execution_plan: list[str]
    parallel_targets: list[str]
    supervisor_plan: dict | None  # serialized SupervisorPlan

    # ── Parallel agent outputs ───────────────────────────────────────────────
    destination_info: dict | None       # serialized DestinationInfo
    flight_results: dict | None         # serialized FlightSearchResult
    hotel_results: dict | None          # serialized HotelSearchResult
    experience_results: list[dict]         # list of serialized Experience

    # ── Sequential agent outputs ─────────────────────────────────────────────
    budget_analysis: dict | None        # serialized BudgetAnalysis
    itinerary: dict | None             # serialized Itinerary
    validation_result: dict | None     # serialized ValidationResult
    booking_result: dict | None        # serialized BookingResult

    # ── User memory / context ────────────────────────────────────────────────
    user_context: dict | None          # loaded from ChromaDB

    # ── HITL ─────────────────────────────────────────────────────────────────
    human_feedback: str | None
    human_approved: bool | None

    # ── Revision feedback (set by validator on failure, consumed by itinerary) ─
    revision_feedback: str | None

    # ── Control flow ─────────────────────────────────────────────────────────
    revision_count: int
    status: str   # queued | running | paused_hitl | complete | failed
    errors: Annotated[list[dict], operator.add]

    # ── Observability ────────────────────────────────────────────────────────
    agent_timings: Annotated[dict[str, float], _merge_dicts]   # agent_name → duration_ms
