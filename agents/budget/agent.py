from __future__ import annotations

import time

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from agents.llm_factory import get_llm_for_agent
from agents.state import TravelState
from prompts.loader import get_prompt
from schemas.budget import BudgetAnalysis
from tools.registry import ToolRegistry


async def budget_node(state: TravelState) -> dict:
    """
    Budget Agent: synthesizes cost data from flights, hotels, and experiences
    into a tiered BudgetAnalysis.
    """
    t0 = time.monotonic()
    agent_name = "budget"

    llm = get_llm_for_agent(agent_name)
    tools = ToolRegistry.get_for_agent(agent_name)
    llm_with_tools = llm.bind_tools(tools)
    structured_llm = llm.with_structured_output(BudgetAnalysis, method="function_calling")

    system_prompt = get_prompt(agent_name)
    constraints = state.get("constraints", {})
    num_travelers = constraints.get("num_travelers", 1)
    num_days = constraints.get("duration_days") or _calc_days(
        constraints.get("departure_date"), constraints.get("return_date")
    )
    budget_usd = constraints.get("budget_usd")
    budget_tier = constraints.get("budget_tier", "mid")

    flight_summary = _summarize_flights(state.get("flight_results"))
    hotel_summary = _summarize_hotels(state.get("hotel_results"))
    exp_summary = _summarize_experiences(state.get("experience_results", []))

    # Optional: currency conversion if destination uses non-USD currency
    dest_info = state.get("destination_info") or {}
    local_currency = dest_info.get("currency", "USD")
    currency_context = ""
    if local_currency and local_currency != "USD":
        messages = [
            SystemMessage(content="You are a currency tool caller."),
            HumanMessage(content=f"Convert 1 USD to {local_currency} using the convert_currency tool."),
        ]
        current_messages = list(messages)
        for _ in range(2):
            response = await llm_with_tools.ainvoke(current_messages)
            if not response.tool_calls:
                break
            current_messages.append(response)
            for tc in response.tool_calls:
                tool_fn = ToolRegistry.get(tc["name"])
                result = await tool_fn.ainvoke(tc["args"])
                currency_context = f"\nLocal currency conversion: {result}"
                current_messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
            break

    synthesis_messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=(
                f"Produce a BudgetAnalysis for this trip:\n\n"
                f"Travelers: {num_travelers}, Days: {num_days}\n"
                f"User budget: {'$' + str(budget_usd) if budget_usd else 'not specified'} ({budget_tier} tier)\n\n"
                f"Flight data:\n{flight_summary}\n\n"
                f"Hotel data:\n{hotel_summary}\n\n"
                f"Experiences data:\n{exp_summary}"
                f"{currency_context}"
            )
        ),
    ]

    budget: BudgetAnalysis = await structured_llm.ainvoke(synthesis_messages)

    duration_ms = round((time.monotonic() - t0) * 1000)
    timings = dict(state.get("agent_timings", {}))
    timings[agent_name] = duration_ms

    return {
        "budget_analysis": budget.model_dump(),
        "agent_timings": timings,
    }


def _calc_days(dep: str | None, ret: str | None) -> int:
    if not dep or not ret:
        return 7
    from datetime import date
    try:
        return max(1, (date.fromisoformat(ret) - date.fromisoformat(dep)).days)
    except Exception:
        return 7


def _summarize_flights(fr: dict | None) -> str:
    if not fr:
        return "No flight data available."
    opts = fr.get("options", [])
    if not opts:
        return "No flight options found."
    cheapest = fr.get("cheapest_usd", "?")
    fastest = fr.get("fastest_minutes", "?")
    return (
        f"{len(opts)} flight options found. "
        f"Cheapest: ${cheapest}. Fastest: {fastest} min. "
        f"Airlines: {', '.join(set(o.get('airline','') for o in opts[:3]))}"
    )


def _summarize_hotels(hr: dict | None) -> str:
    if not hr:
        return "No hotel data available."
    opts = hr.get("options", [])
    if not opts:
        return "No hotel options found."
    ppn_range = f"${opts[0].get('price_per_night_usd', '?')} – ${opts[-1].get('price_per_night_usd', '?')}"
    return (
        f"{len(opts)} hotel options. "
        f"Price per night: {ppn_range}. "
        f"Stars: {opts[0].get('star_rating', '?')}–{opts[-1].get('star_rating', '?')}"
    )


def _summarize_experiences(exps: list[dict]) -> str:
    if not exps:
        return "No experiences data available."
    cats = set(e.get("category", "") for e in exps)
    return f"{len(exps)} experiences across categories: {', '.join(cats)}"
