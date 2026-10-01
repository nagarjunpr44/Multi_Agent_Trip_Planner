from __future__ import annotations

import json
import time
from datetime import date, timedelta

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from agents.itinerary.context import build_itinerary_context
from agents.llm_factory import get_llm_for_agent
from agents.state import TravelState
from prompts.loader import get_prompt
from schemas.itinerary import DayPlan, Itinerary
from tools.registry import ToolRegistry


async def itinerary_node(state: TravelState) -> dict:
    """
    Itinerary Agent: builds a day-by-day Itinerary from all parallel agent outputs.
    Enrichment and autonomous revision happen in downstream nodes.
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
    destination = (
        dest_info.get("city")
        or (constraints.get("destinations") or [None])[0]
        or constraints.get("destination", "")
    )

    experiences: list[dict] = state.get("experience_results", [])
    distance_context = ""
    if len(experiences) >= 2 and tools:
        try:
            distance_context = await _fetch_sample_distances(
                experiences[:4], destination, llm_with_tools
            )
        except Exception:
            distance_context = ""

    day_labels = _generate_day_labels(departure_date, num_days)
    context_block = build_itinerary_context(
        state, num_days, num_travelers, destination, day_labels
    )

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
                "Distance context (for realistic scheduling):\n"
                f"{distance_context or 'Not available.'}"
                f"{revision_section}\n\n"
                f"Produce a full day-by-day Itinerary with exactly {num_days} DayPlans.\n"
                "MANDATORY per Activity:\n"
                "- description: 80+ chars (what, why, local tip)\n"
                "- location: street/neighborhood or landmark\n"
                "- start_time: HH:MM, duration_minutes: realistic\n"
                "- booking_url or maps_url when available\n"
                "- transport_from_previous when changing venues\n"
                "Prefer verified experiences from context."
            )
        ),
    ]

    itinerary: Itinerary = await structured_llm.ainvoke(messages)
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
            try:
                result = await tool_fn.ainvoke(tc["args"])
            except Exception as exc:
                result = json.dumps({"error": str(exc)})
            results.append(str(result))
            current_messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
        break
    return "\n".join(results)


def _calc_days(dep: str | None, ret: str | None, constraints: dict | None = None) -> int:
    if constraints and constraints.get("duration_days"):
        return int(constraints["duration_days"])
    if dep and ret:
        try:
            return max(1, (date.fromisoformat(ret) - date.fromisoformat(dep)).days)
        except (ValueError, TypeError):
            pass
    return 3


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
