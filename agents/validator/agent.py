from __future__ import annotations

import time

from agents.llm_factory import get_llm_for_agent
from agents.orchestrator.agent import _activity_detail_score
from agents.state import TravelState
from prompts.loader import get_prompt
from schemas.agent_output import ValidationResult


async def validator_node(state: TravelState) -> dict:
    """
    Validator Agent — scores plan quality. Routing is delegated to orchestrator_node.
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

    detail_score = _activity_detail_score(itinerary)
    validation_prompt = _build_validation_prompt(
        constraints,
        itinerary,
        budget_analysis,
        flight_results,
        hotel_results,
        experience_results,
        detail_score,
    )

    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=validation_prompt),
    ]

    result: ValidationResult = await structured_llm.ainvoke(messages)
    result.detail_score = detail_score

    # Fail if activities are vague even when other scores are OK
    if detail_score < 0.6:
        result.passed = False
        result.quality_score = min(result.quality_score, detail_score)
        result.issues = list(result.issues) + [
            "Activities lack detail (descriptions, times, addresses, or links)."
        ]

    duration_ms = round((time.monotonic() - t0) * 1000)
    timings = dict(state.get("agent_timings", {}))
    timings[agent_name] = duration_ms

    new_revision_count = revision_count if result.passed else revision_count + 1

    revision_feedback: str | None = None
    if not result.passed:
        issues_str = (
            "\n".join(f"• {issue}" for issue in result.issues)
            if result.issues
            else "No specific issues listed."
        )
        suggestions_str = (
            "\n".join(f"• {s}" for s in result.suggestions)
            if result.suggestions
            else "No suggestions provided."
        )
        revision_feedback = (
            f"ISSUES TO FIX:\n{issues_str}\n\n"
            f"SUGGESTIONS TO INCORPORATE:\n{suggestions_str}\n\n"
            f"DIMENSION SCORES:\n"
            f"  Feasibility:      {result.feasibility_score:.2f}\n"
            f"  Budget alignment: {result.budget_alignment_score:.2f}\n"
            f"  Coverage:         {result.coverage_score:.2f}\n"
            f"  Quality:          {result.quality_score:.2f}\n"
            f"  Detail:           {detail_score:.2f}\n"
            f"  Overall:          {result.score:.2f} (need ≥ 0.75 to pass)"
        )

    return {
        "validation_result": result.model_dump(),
        "revision_count": new_revision_count,
        "revision_feedback": revision_feedback,
        "agent_timings": timings,
    }


def _build_validation_prompt(
    constraints: dict,
    itinerary: dict,
    budget_analysis: dict,
    flight_results: dict,
    hotel_results: dict,
    experience_results: list[dict],
    detail_score: float,
) -> str:
    destination = constraints.get("destination") or (
        (constraints.get("destinations") or ["Unknown"])[0]
    )
    num_travelers = constraints.get("num_travelers", 1)
    budget_usd = constraints.get("budget_usd")
    budget_tier = constraints.get("budget_tier", "mid")
    preferences = constraints.get("activity_preferences") or constraints.get("preferences", [])

    days = itinerary.get("days", [])
    num_days = len(days)
    sample_activities = []
    for day in days[:2]:
        for slot in ("morning", "afternoon", "evening"):
            for act in (day.get(slot) or [])[:2]:
                sample_activities.append(
                    f"{act.get('name')}: desc={len(act.get('description') or '')} chars, "
                    f"loc={act.get('location', 'missing')}, "
                    f"start={act.get('start_time', 'missing')}"
                )

    mid_budget = (budget_analysis.get("mid") or {}).get("total_usd", "unknown")
    num_flights = len(flight_results.get("options") or [])
    num_hotels = len(hotel_results.get("options") or [])
    num_experiences = len(experience_results)

    return (
        f"Validate this travel plan:\n\n"
        f"DESTINATION: {destination}\n"
        f"TRAVELERS: {num_travelers} | DURATION: {num_days} days\n"
        f"USER BUDGET: {'$' + str(budget_usd) if budget_usd else 'unspecified'} ({budget_tier})\n"
        f"PREFERENCES: {', '.join(preferences) if preferences else 'none'}\n\n"
        f"ACTIVITY DETAIL SCORE (heuristic): {detail_score:.2f}\n"
        f"SAMPLE ACTIVITIES:\n" + "\n".join(sample_activities[:6]) + "\n\n"
        f"DATA: flights={num_flights}, hotels={num_hotels}, experiences={num_experiences}\n"
        f"Mid-tier budget: ${mid_budget}\n\n"
        "Score strictly on feasibility, budget, coverage, and QUALITY/DETAIL.\n"
        "FAIL if activities are name+location only without descriptions, times, or links.\n"
        "PASS threshold = 0.75 overall AND detail_score >= 0.6."
    )
