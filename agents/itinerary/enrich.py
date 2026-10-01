from __future__ import annotations

import json
import time

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from agents.itinerary.agent import _backfill_dates, _calc_days, _generate_day_labels
from agents.itinerary.context import build_itinerary_context
from agents.llm_factory import get_llm_for_agent
from agents.state import TravelState
from prompts.loader import get_prompt
from schemas.itinerary import Itinerary
from tools.registry import ToolRegistry
from langgraph.prebuilt import create_react_agent


async def itinerary_enrich_node(state: TravelState) -> dict:
    """
    Autonomous enrichment pass — ReAct agent uses web/places/distance tools to expand
    each activity with descriptions, times, URLs, and logistics before validation.
    """
    t0 = time.monotonic()
    agent_name = "itinerary_enrich"

    llm = get_llm_for_agent(agent_name)
    tools = ToolRegistry.get_for_agent(agent_name)
    system_prompt = get_prompt(agent_name)
    structured_llm = llm.with_structured_output(Itinerary, method="function_calling")

    constraints = state.get("constraints", {})
    departure_date = constraints.get("departure_date")
    return_date = constraints.get("return_date")
    num_travelers = constraints.get("num_travelers", 1)
    num_days = _calc_days(departure_date, return_date, constraints)
    dest_info = state.get("destination_info") or {}
    destination = (
        dest_info.get("city")
        or (constraints.get("destinations") or [None])[0]
        or constraints.get("destination", "")
    )
    day_labels = _generate_day_labels(departure_date, num_days)
    context_block = build_itinerary_context(
        state, num_days, num_travelers, destination, day_labels
    )

    current_itinerary = state.get("itinerary") or {}
    revision_feedback = state.get("revision_feedback") or ""

    react_agent = create_react_agent(llm, tools, prompt=system_prompt)
    agent_result = await react_agent.ainvoke({
        "messages": [
            HumanMessage(
                content=(
                    f"Enrich trip to {destination} ({num_days} days).\n"
                    f"User query: {state['user_query']}\n\n"
                    "For EVERY activity in the draft itinerary, use tools to find:\n"
                    "- opening hours, booking links, exact address\n"
                    "- walking/transit time from previous stop\n"
                    "- 2-3 sentence why_visit description with local tips\n\n"
                    f"Draft itinerary JSON:\n{json.dumps(current_itinerary)[:6000]}\n\n"
                    f"Context:\n{context_block[:4000]}\n\n"
                    f"Validator feedback:\n{revision_feedback or 'none'}"
                )
            )
        ]
    })

    tool_results = [
        str(m.content)
        for m in agent_result.get("messages", [])
        if isinstance(m, ToolMessage)
    ]

    synthesis_messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=(
                f"Produce an enriched Itinerary for {destination} with exactly {num_days} days.\n"
                "Every Activity MUST include:\n"
                "- description: at least 80 characters (what, why, tips)\n"
                "- location: full address or landmark + neighborhood\n"
                "- duration_minutes: realistic integer\n"
                "- start_time: HH:MM (24h)\n"
                "- booking_url when bookable (or null)\n"
                "- maps_url: Google Maps search URL for the venue\n\n"
                f"Draft to enrich:\n{json.dumps(current_itinerary)[:5000]}\n\n"
                f"Tool research:\n" + "\n---\n".join(tool_results[-8:])
            )
        ),
    ]

    itinerary: Itinerary = await structured_llm.ainvoke(synthesis_messages)
    itinerary = _backfill_dates(itinerary, departure_date, num_days)

    duration_ms = round((time.monotonic() - t0) * 1000)
    timings = dict(state.get("agent_timings", {}))
    timings[agent_name] = duration_ms

    enrich_count = state.get("enrich_cycle_count", 0)

    return {
        "itinerary": itinerary.model_dump(),
        "enrich_cycle_count": enrich_count + 1,
        "agent_timings": timings,
    }
