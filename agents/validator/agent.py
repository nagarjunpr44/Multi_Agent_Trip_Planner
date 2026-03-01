from __future__ import annotations

import time

from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm_factory import get_llm_for_agent
from agents.state import TravelState
from prompts.loader import get_prompt
from schemas.agent_output import ValidationResult


async def validator_node(state: TravelState) -> dict:
    """
    Validator Agent: quality-critic that scores the itinerary across four dimensions.
    If score < 0.75 and revision_count < 2, the graph loops back for another planning pass.
    """
    t0 = time.monotonic()
    agent_name = "validator"

    llm = get_llm_for_agent(agent_name)
    structured_llm = llm.with_structured_output(ValidationResult, method="function_calling")

    system_prompt = get_prompt(agent_name)
    constraints = state.get("constraints", {})
    itinerary = state.get("itinerary") or {}
    budget_analysis = state.get("budget_analysis") or {}
    flight_results = state.get("flight_results") or {}
    hotel_results = state.get("hotel_results") or {}
    experience_results = state.get("experience_results") or []
    revision_count = state.get("revision_count", 0)

    validation_prompt = _build_validation_prompt(
        constraints, itinerary, budget_analysis, flight_results, hotel_results, experience_results
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=validation_prompt),
    ]

    result: ValidationResult = await structured_llm.ainvoke(messages)

    duration_ms = round((time.monotonic() - t0) * 1000)
    timings = dict(state.get("agent_timings", {}))
    timings[agent_name] = duration_ms

    new_revision_count = revision_count if result.passed else revision_count + 1

    return {
        "validation_result": result.model_dump(),
        "revision_count": new_revision_count,
        "agent_timings": timings,
    }


def _build_validation_prompt(
    constraints: dict,
    itinerary: dict,
    budget_analysis: dict,
    flight_results: dict,
    hotel_results: dict,
    experience_results: list[dict],
) -> str:
    destination = constraints.get("destination", "Unknown")
    num_travelers = constraints.get("num_travelers", 1)
    budget_usd = constraints.get("budget_usd")
    budget_tier = constraints.get("budget_tier", "mid")
    preferences = constraints.get("preferences", [])
    avoid = constraints.get("avoid", [])

    days = itinerary.get("days", [])
    num_days = len(days)
    highlights = itinerary.get("highlights", [])
    total_est = itinerary.get("total_estimated_cost_usd", "unknown")

    mid_budget = (budget_analysis.get("mid") or {}).get("total_cost_usd", "unknown")

    num_flights = len((flight_results.get("options") or []))
    num_hotels = len((hotel_results.get("options") or []))
    num_experiences = len(experience_results)

    pref_str = ", ".join(preferences) if preferences else "none specified"
    avoid_str = ", ".join(avoid) if avoid else "none"
    hl_str = ", ".join(highlights[:5]) if highlights else "none"
    daily_themes = [(d.get("theme") or f"Day {d.get('day_number', i+1)}") for i, d in enumerate(days[:4])]

    return (
        f"Validate this travel plan:\n\n"
        f"DESTINATION: {destination}\n"
        f"TRAVELERS: {num_travelers} | DURATION: {num_days} days\n"
        f"USER BUDGET: {'$' + str(budget_usd) if budget_usd else 'unspecified'} "
        f"({budget_tier} tier)\n"
        f"PREFERENCES: {pref_str}\n"
        f"AVOID: {avoid_str}\n\n"
        f"ITINERARY OVERVIEW:\n"
        f"  Highlights: {hl_str}\n"
        f"  Day themes: {', '.join(daily_themes)}\n"
        f"  Total days planned: {num_days}\n"
        f"  Estimated total cost: ${total_est}\n"
        f"  Estimated mid budget: ${mid_budget}\n\n"
        f"DATA COVERAGE:\n"
        f"  Flights found: {num_flights}\n"
        f"  Hotels found: {num_hotels}\n"
        f"  Experiences found: {num_experiences}\n\n"
        f"Score the plan on:\n"
        f"1. Completeness (all days filled, all data present)\n"
        f"2. Budget adherence (within user budget or justified)\n"
        f"3. Preference match (aligns with user preferences, avoids stated avoidances)\n"
        f"4. Feasibility (travel times realistic, activity count per day reasonable)\n\n"
        f"Return a ValidationResult with score (0.0–1.0), passed (true if score >= 0.75), "
        f"issues list, and suggestions list. Be strict — a score of 0.75 means 'barely acceptable'."
    )
