from __future__ import annotations

import time
from datetime import date, timedelta

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from agents.llm_factory import get_llm_for_agent
from agents.state import TravelState
from prompts.loader import get_prompt
from schemas.itinerary import Activity, DayPlan, Itinerary
from tools.registry import ToolRegistry


async def itinerary_node(state: TravelState) -> dict:
    """
    Itinerary Agent: builds a day-by-day Itinerary from all parallel agent outputs.
    Uses the get_travel_distance tool to add realistic travel times between activities.
    """
    t0 = time.monotonic()
    agent_name = "itinerary"

    llm = get_llm_for_agent(agent_name)
    tools = ToolRegistry.get_for_agent(agent_name)
    llm_with_tools = llm.bind_tools(tools)
    structured_llm = llm.with_structured_output(Itinerary, method="function_calling")

    system_prompt = get_prompt(agent_name)
    constraints = state.get("constraints", {})
    departure_date = constraints.get("departure_date")
    return_date = constraints.get("return_date")
    num_travelers = constraints.get("num_travelers", 1)

    num_days = _calc_days(departure_date, return_date)
    dest_info = state.get("destination_info") or {}
    destination = dest_info.get("city") or constraints.get("destination", "")

    # Gather distance between top activities to enrich the itinerary prompt
    experiences: list[dict] = state.get("experience_results", [])
    distance_context = ""
    if len(experiences) >= 2 and tools:
        distance_context = await _fetch_sample_distances(
            experiences[:4], destination, llm_with_tools
        )

    day_labels = _generate_day_labels(departure_date, num_days)

    context_block = _build_context_block(state, num_days, num_travelers, destination, day_labels)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=(
                f"{context_block}\n\n"
                f"Distance context (for realistic scheduling):\n{distance_context or 'Not available.'}\n\n"
                "Produce a full day-by-day Itinerary with exactly "
                f"{num_days} DayPlans. "
                "Each day should have 3–5 activities. "
                "Total estimated cost should be consistent with the budget analysis."
            )
        ),
    ]

    itinerary: Itinerary = await structured_llm.ainvoke(messages)

    # Back-fill dates if LLM left them empty
    itinerary = _backfill_dates(itinerary, departure_date, num_days)

    duration_ms = round((time.monotonic() - t0) * 1000)
    timings = dict(state.get("agent_timings", {}))
    timings[agent_name] = duration_ms

    return {
        "itinerary": itinerary.model_dump(),
        "agent_timings": timings,
    }


async def _fetch_sample_distances(
    experiences: list[dict], destination: str, llm_with_tools
) -> str:
    """Call get_travel_distance for pairs of nearby activities."""
    results = []
    msgs = [
        SystemMessage(content="You call the get_travel_distance tool to get travel times."),
        HumanMessage(
            content="\n".join(
                f"Get walking duration from '{experiences[i].get('name', destination)}' "
                f"to '{experiences[i + 1].get('name', destination)}'."
                for i in range(min(2, len(experiences) - 1))
            )
        ),
    ]
    current_messages = list(msgs)
    for _ in range(4):
        response = await llm_with_tools.ainvoke(current_messages)
        if not response.tool_calls:
            break
        current_messages.append(response)
        for tc in response.tool_calls:
            tool_fn = ToolRegistry.get(tc["name"])
            result = await tool_fn.ainvoke(tc["args"])
            results.append(str(result))
            current_messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
        if not results:
            break
        # Only need first batch
        break
    return "\n".join(results)


def _calc_days(dep: str | None, ret: str | None) -> int:
    if not dep or not ret:
        return 7
    try:
        return max(1, (date.fromisoformat(ret) - date.fromisoformat(dep)).days)
    except Exception:
        return 7


def _generate_day_labels(departure_date: str | None, num_days: int) -> list[str]:
    if not departure_date:
        return [f"Day {i + 1}" for i in range(num_days)]
    try:
        start = date.fromisoformat(departure_date)
        return [(start + timedelta(days=i)).isoformat() for i in range(num_days)]
    except Exception:
        return [f"Day {i + 1}" for i in range(num_days)]


def _backfill_dates(itinerary: Itinerary, departure_date: str | None, num_days: int) -> Itinerary:
    if not departure_date:
        return itinerary
    try:
        start = date.fromisoformat(departure_date)
        day_plans = []
        for i, dp in enumerate(itinerary.days):
            if not dp.date:
                dp = DayPlan(
                    date=(start + timedelta(days=i)).isoformat(),
                    day_number=dp.day_number or i + 1,
                    theme=dp.theme,
                    activities=dp.activities,
                    estimated_cost_usd=dp.estimated_cost_usd,
                    notes=dp.notes,
                )
            day_plans.append(dp)
        return Itinerary(
            destination=itinerary.destination,
            days=day_plans,
            total_estimated_cost_usd=itinerary.total_estimated_cost_usd,
            highlights=itinerary.highlights,
            tips=itinerary.tips,
        )
    except Exception:
        return itinerary


def _build_context_block(
    state: TravelState,
    num_days: int,
    num_travelers: int,
    destination: str,
    day_labels: list[str],
) -> str:
    dest_info = state.get("destination_info") or {}
    budget_analysis = state.get("budget_analysis") or {}
    flight_results = state.get("flight_results") or {}
    hotel_results = state.get("hotel_results") or {}
    experiences = state.get("experience_results", [])

    flight_info = "No flight data."
    if flight_results.get("options"):
        fo = flight_results["options"][0]
        flight_info = (
            f"Selected flight: {fo.get('airline', 'N/A')} | "
            f"${fo.get('total_price_usd', 'N/A')} | "
            f"{fo.get('duration_minutes', 'N/A')} min"
        )

    hotel_info = "No hotel data."
    if hotel_results.get("options"):
        ho = hotel_results["options"][0]
        hotel_info = (
            f"Selected hotel: {ho.get('name', 'N/A')} | "
            f"${ho.get('price_per_night_usd', 'N/A')}/night | "
            f"{ho.get('star_rating', 'N/A')} stars"
        )

    exp_names = [e.get("name", "") for e in experiences[:10]]
    exp_info = ", ".join(exp_names) if exp_names else "None"

    mid = budget_analysis.get("mid", {})
    budget_total = mid.get("total_cost_usd", "unknown")

    return (
        f"Destination: {destination}\n"
        f"Trip duration: {num_days} days | Travelers: {num_travelers}\n"
        f"Day labels: {', '.join(day_labels)}\n\n"
        f"Destination highlights: {', '.join(dest_info.get('highlights', []))}\n"
        f"Local tips: {', '.join(dest_info.get('local_tips', []))}\n"
        f"Best season: {dest_info.get('best_season', 'N/A')}\n\n"
        f"Flight: {flight_info}\n"
        f"Hotel: {hotel_info}\n"
        f"Activities available: {exp_info}\n\n"
        f"Total budget target: ${budget_total}"
    )
