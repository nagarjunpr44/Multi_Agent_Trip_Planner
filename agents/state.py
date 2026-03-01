from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


def _merge_dicts(a: dict, b: dict) -> dict:
    """Merge reducer for dict-typed state fields updated by parallel nodes."""
    return {**a, **b}

from schemas.agent_output import (
    BookingResult,
    DestinationInfo,
    SupervisorPlan,
    ValidationResult,
)
from schemas.budget import BudgetAnalysis
from schemas.flight import FlightSearchResult
from schemas.hotel import HotelSearchResult
from schemas.itinerary import Experience, Itinerary


class TravelState(TypedDict):
    # ── Input ───────────────────────────────────────────────────────────────
    session_id: str
    user_query: str
    constraints: dict[str, Any]  # serialized TripConstraints
    mode: Literal["autonomous", "hitl"]

    # ── Conversation history (LangGraph reducer merges lists) ────────────────
    messages: Annotated[list[BaseMessage], add_messages]

    # ── Supervisor plan ──────────────────────────────────────────────────────
    execution_plan: list[str]
    parallel_targets: list[str]
    supervisor_plan: Optional[dict]  # serialized SupervisorPlan

    # ── Parallel agent outputs ───────────────────────────────────────────────
    destination_info: Optional[dict]       # serialized DestinationInfo
    flight_results: Optional[dict]         # serialized FlightSearchResult
    hotel_results: Optional[dict]          # serialized HotelSearchResult
    experience_results: list[dict]         # list of serialized Experience

    # ── Sequential agent outputs ─────────────────────────────────────────────
    budget_analysis: Optional[dict]        # serialized BudgetAnalysis
    itinerary: Optional[dict]             # serialized Itinerary
    validation_result: Optional[dict]     # serialized ValidationResult
    booking_result: Optional[dict]        # serialized BookingResult

    # ── User memory / context ────────────────────────────────────────────────
    user_context: Optional[dict]          # loaded from ChromaDB

    # ── HITL ─────────────────────────────────────────────────────────────────
    human_feedback: Optional[str]
    human_approved: Optional[bool]

    # ── Control flow ─────────────────────────────────────────────────────────
    revision_count: int
    status: str   # queued | running | paused_hitl | complete | failed
    errors: Annotated[list[dict], operator.add]

    # ── Observability ────────────────────────────────────────────────────────
    agent_timings: Annotated[dict[str, float], _merge_dicts]   # agent_name → duration_ms
