from __future__ import annotations

import operator
from typing import Annotated, Any, Literal

from langgraph.graph import MessagesState


def _merge_dicts(a: dict, b: dict) -> dict:
    """Merge reducer for dict-typed state fields updated by parallel nodes."""
    return {**a, **b}



def _merge_experiences(existing: list, new: list) -> list:
    """Merge experience lists by name (used when coverage re-dispatches gather agents)."""
    by_name: dict[str, dict] = {}
    for item in existing or []:
        name = (item.get("name") or "").strip().lower()
        if name:
            by_name[name] = item
    for item in new or []:
        name = (item.get("name") or "").strip().lower()
        if name and name not in by_name:
            by_name[name] = item
    return list(by_name.values())


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
    experience_results: Annotated[list[dict], _merge_experiences]  # list of serialized Experience

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
    gather_cycle_count: int
    enrich_cycle_count: int
    replenish_targets: list[str]
    coverage_notes: str | None
    orchestrator_decision: dict | None
    status: str   # queued | running | paused_hitl | complete | failed
    errors: Annotated[list[dict], operator.add]

    # ── Observability ────────────────────────────────────────────────────────
    agent_timings: Annotated[dict[str, float], _merge_dicts]   # agent_name → duration_ms
