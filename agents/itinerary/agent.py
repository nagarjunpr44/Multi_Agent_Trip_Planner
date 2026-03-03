from __future__ import annotations

import time
from datetime import date, timedelta

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from agents.llm_factory import get_llm_for_agent
from agents.state import TravelState
from prompts.loader import get_prompt
from schemas.itinerary import DayPlan, Itinerary
from tools.registry import ToolRegistry


async def itinerary_node(state: TravelState) -> dict:
    """
    Itinerary Agent: builds a day-by-day Itinerary from all parallel agent outputs.

    On revision passes (revision_count > 0), injects the validator's structured
    feedback so the agent knows exactly what to fix rather than regenerating blindly.
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
    revision_count = state.get("revision_count", 0)
    revision_feedback = state.get("revision_feedback")

    num_days = _calc_days(departure_date, return_date, constraints)
    dest_info = state.get("destination_info") or {}
    # Check city, then destinations list, then legacy singular destination key
    destination = (
        dest_info.get("city")
        or (constraints.get("destinations") or [None])[0]
        or constraints.get("destination", "")
    )

    # Fetch travel distances between top activities for scheduling context
    experiences: list[dict] = state.get("experience_results", [])
    distance_context = ""
    if len(experiences) >= 2 and tools:
        distance_context = await _fetch_sample_distances(
            experiences[:4], destination, llm_with_tools
        )

    day_labels = _generate_day_labels(departure_date, num_days)
    context_block = _build_context_block(state, num_days, num_travelers, destination, day_labels)

    # On revision passes, tell the agent exactly what the validator flagged
    revision_section = ""
    if revision_count > 0 and revision_feedback:
        revision_section = (
            f"\n\n⚠️  REVISION {revision_count} — The previous itinerary did NOT pass validation.\n"
            f"You MUST address the following specific issues in this revision:\n\n"
            f"{revision_feedback}\n\n"
            f"Keep activities and daily structure largely the same; fix only the flagged problems."
        )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=(
                f"{context_block}\n\n"
                f"Distance context (for realistic scheduling):\n{distance_context or 'Not available.'}"
                f"{revision_section}\n\n"
                f"Produce a full day-by-day Itinerary with exactly {num_days} DayPlans. "
                "Each day should have 3–5 activities. "
                "Total estimated cost should be consistent with the budget analysis."
            )
        ),
    ]

    itinerary: Itinerary = await structured_llm.ainvoke(messages)

    # Back-fill dates if the LLM left them empty
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
        # One batch is enough
        break
    return "\n".join(results)


def _calc_days(dep: str | None, ret: str | None, constraints: dict | None = None) -> int:
    # First check if constraints has explicit duration_days
    if constraints and constraints.get("duration_days"):
        return int(constraints["duration_days"])
    if dep and ret:
        try:
            return max(1, (date.fromisoformat(ret) - date.fromisoformat(dep)).days)
        except (ValueError, TypeError):
            pass
    return 3  # sensible default instead of 7


def _generate_day_labels(departure_date: str | None, num_days: int) -> list[str]:
    if not departure_date:
        return [f"Day {i + 1}" for i in range(num_days)]
    try:
        start = date.fromisoformat(departure_date)
        return [(start + timedelta(days=i)).isoformat() for i in range(num_days)]
    except Exception:
        return [f"Day {i + 1}" for i in range(num_days)]


def _backfill_dates(itinerary: Itinerary, departure_date: str | None, num_days: int) -> Itinerary:
    """Fill in missing `date` fields on DayPlans using the departure date."""
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
                    city=dp.city,
                    theme=dp.theme,
                    morning=dp.morning,
                    afternoon=dp.afternoon,
                    evening=dp.evening,
                    travel_between_venues_minutes=dp.travel_between_venues_minutes,
                    day_total_cost_usd=dp.day_total_cost_usd,
                    notes=dp.notes,
                )
            day_plans.append(dp)
        return Itinerary(
            title=itinerary.title,
            destination=itinerary.destination,
            num_days=itinerary.num_days,
            num_travelers=itinerary.num_travelers,
            days=day_plans,
            total_activities_cost_usd=itinerary.total_activities_cost_usd,
            highlights=itinerary.highlights,
            travel_tips=itinerary.travel_tips,
            best_neighborhoods=itinerary.best_neighborhoods,
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
            f"{fo.get('duration_minutes', 'N/A')} min | "
            f"Departs: {fo.get('departure_time', 'N/A')} -> Arrives: {fo.get('arrival_time', 'N/A')}"
        )

    hotel_info = "No hotel data."
    if hotel_results.get("options"):
        ho = hotel_results["options"][0]
        hotel_info = (
            f"Selected hotel: {ho.get('name', 'N/A')} | "
            f"${ho.get('price_per_night_usd', 'N/A')}/night | "
            f"{ho.get('star_rating', 'N/A')} stars | "
            f"Address: {ho.get('address', 'N/A')}"
        )

    # Feed full experience details so LLM can create specific plans
    exp_lines = []
    for e in experiences[:12]:
        line = f"- {e.get('name', 'N/A')}"
        if e.get("address"):
            line += f" | {e['address']}"
        if e.get("rating"):
            line += f" | Rating: {e['rating']}"
        if e.get("category"):
            line += f" | [{e['category']}]"
        if e.get("description"):
            line += f"\n  {e['description'][:120]}"
        exp_lines.append(line)
    exp_info = "\n".join(exp_lines) if exp_lines else "No activity data available."

    # BudgetTier field is total_usd (not total_cost_usd)
    mid = budget_analysis.get("mid") or {}
    budget_total = mid.get("total_usd", "unknown")

    budget_info = f"Total budget target: ${budget_total}"
    if mid:
        budget_info += (
            f"\n  Activities: ${mid.get('activities_usd', 'N/A')} | "
            f"Food: ${mid.get('food_usd', 'N/A')} | "
            f"Transport: ${mid.get('transport_usd', 'N/A')}"
        )

    return (
        f"Destination: {destination}\n"
        f"Trip duration: {num_days} days | Travelers: {num_travelers}\n"
        f"Day labels: {', '.join(day_labels)}\n\n"
        f"Destination highlights: {', '.join(dest_info.get('highlights', []))}\n"
        f"Local tips: {', '.join(dest_info.get('local_tips', []))}\n"
        f"Best season: {dest_info.get('best_season', 'N/A')}\n\n"
        f"Flight: {flight_info}\n"
        f"Hotel: {hotel_info}\n\n"
        f"Activities available:\n{exp_info}\n\n"
        f"{budget_info}"
    )
