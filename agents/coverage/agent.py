from __future__ import annotations

import time

from langgraph.types import Command, Send

from agents.state import TravelState
from config.settings import get_settings

MIN_EXPERIENCES = 8
MIN_FLIGHT_OPTIONS = 1
MIN_HOTEL_OPTIONS = 1


async def coverage_node(state: TravelState) -> Command:
    """
    Autonomous coverage gate — inspects gathered data and either proceeds to budget
    or re-dispatches parallel agents to fill gaps (up to max_gather_cycles).
    """
    t0 = time.monotonic()
    settings = get_settings()
    max_cycles = settings.app.max_gather_cycles
    cycle = state.get("gather_cycle_count", 0)

    flight_results = state.get("flight_results") or {}
    hotel_results = state.get("hotel_results") or {}
    experiences = state.get("experience_results") or []
    dest_info = state.get("destination_info") or {}
    constraints = state.get("constraints") or {}

    num_flights = len(flight_results.get("options") or [])
    num_hotels = len(hotel_results.get("options") or [])
    num_experiences = len(experiences)
    has_research = bool(dest_info.get("highlights") or dest_info.get("local_tips"))

    replenish: list[str] = []
    notes: list[str] = []

    if num_experiences < MIN_EXPERIENCES:
        replenish.append("experiences_node")
        notes.append(f"experiences={num_experiences} (need {MIN_EXPERIENCES}+)")
    if num_flights < MIN_FLIGHT_OPTIONS and constraints.get("origin_city"):
        replenish.append("flights_node")
        notes.append("no flight options")
    if num_hotels < MIN_HOTEL_OPTIONS:
        replenish.append("hotels_node")
        notes.append("no hotel options")
    if not has_research:
        replenish.append("research_node")
        notes.append("thin destination research")

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_replenish = [n for n in replenish if not (n in seen or seen.add(n))]

    duration_ms = round((time.monotonic() - t0) * 1000)
    timings = dict(state.get("agent_timings", {}))
    timings["coverage"] = duration_ms

    coverage_note = "; ".join(notes) if notes else "all coverage thresholds met"

    if unique_replenish and cycle < max_cycles:
        return Command(
            goto=[Send(node, state) for node in unique_replenish],
            update={
                "gather_cycle_count": cycle + 1,
                "replenish_targets": unique_replenish,
                "coverage_notes": coverage_note,
                "agent_timings": timings,
            },
        )

    return Command(
        goto="budget_node",
        update={
            "coverage_notes": coverage_note,
            "agent_timings": timings,
        },
    )
