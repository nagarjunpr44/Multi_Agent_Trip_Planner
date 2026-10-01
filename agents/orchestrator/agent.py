from __future__ import annotations

import time

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Command, Send

from agents.llm_factory import get_llm_for_agent
from agents.state import TravelState
from prompts.loader import get_prompt
from schemas.agent_output import OrchestratorDecision
from schemas.itinerary import Itinerary


def _activity_detail_score(itinerary: dict) -> float:
    """Heuristic: fraction of activities with substantive descriptions."""
    activities = []
    for day in itinerary.get("days") or []:
        for slot in ("morning", "afternoon", "evening"):
            activities.extend(day.get(slot) or [])

    if not activities:
        return 0.0

    detailed = 0
    for act in activities:
        desc = (act.get("description") or "").strip()
        if len(desc) >= 80 and act.get("duration_minutes") and act.get("location"):
            detailed += 1
    return detailed / len(activities)


async def orchestrator_node(state: TravelState) -> Command:
    """
    Autonomous orchestrator — decides the next graph action after validation.
    Can loop enrichment, rebuild itinerary, re-gather data, or finish to booking.
    """
    t0 = time.monotonic()
    agent_name = "orchestrator"

    validation = state.get("validation_result") or {}
    revision_count = state.get("revision_count", 0)
    enrich_count = state.get("enrich_cycle_count", 0)
    gather_cycle = state.get("gather_cycle_count", 0)
    itinerary = state.get("itinerary") or {}
    detail_score = _activity_detail_score(itinerary)

    max_revisions = get_settings().app.max_revision_cycles
    max_enrich = get_settings().app.max_enrich_cycles
    max_gather = get_settings().app.max_gather_cycles

    # Fast path: excellent plan
    if validation.get("passed") and detail_score >= 0.85:
        goto = "booking_node"
        decision = OrchestratorDecision(
            next_action="book",
            reasoning="Validation passed and activity detail threshold met.",
            confidence=0.95,
        )
    elif enrich_count < max_enrich and detail_score < 0.85:
        goto = "itinerary_enrich_node"
        decision = OrchestratorDecision(
            next_action="enrich",
            reasoning=f"Activity detail score {detail_score:.2f} below 0.85 — enrich with tools.",
            confidence=0.9,
        )
    elif (
        not validation.get("passed")
        and revision_count < max_revisions
        and validation.get("coverage_score", 1) >= 0.5
    ):
        goto = "itinerary_node"
        decision = OrchestratorDecision(
            next_action="rebuild",
            reasoning="Validation failed on quality/feasibility — rebuild itinerary.",
            confidence=0.85,
        )
    elif gather_cycle < max_gather and (
        validation.get("coverage_score", 1) < 0.5
        or len(state.get("experience_results") or []) < 6
    ):
        # Re-gather data autonomously
        targets = ["experiences_node", "research_node"]
        if not (state.get("flight_results") or {}).get("options"):
            targets.append("flights_node")
        if not (state.get("hotel_results") or {}).get("options"):
            targets.append("hotels_node")
        seen: set[str] = set()
        nodes = [n for n in targets if not (n in seen or seen.add(n))]
        return Command(
            goto=[Send(n, state) for n in nodes],
            update={
                "gather_cycle_count": gather_cycle + 1,
                "orchestrator_decision": {
                    "next_action": "gather",
                    "reasoning": "Insufficient data coverage — re-dispatching gather agents.",
                },
                "agent_timings": {
                    **dict(state.get("agent_timings", {})),
                    agent_name: round((time.monotonic() - t0) * 1000),
                },
            },
        )
    else:
        goto = "booking_node"
        decision = OrchestratorDecision(
            next_action="book",
            reasoning="Max autonomous cycles reached — proceeding with best available plan.",
            confidence=0.7,
        )

    update: dict = {
        "orchestrator_decision": decision.model_dump(),
        "agent_timings": {
            **dict(state.get("agent_timings", {})),
            agent_name: round((time.monotonic() - t0) * 1000),
        },
    }
    if goto == "itinerary_enrich_node":
        update["enrich_cycle_count"] = enrich_count + 1

    # LLM can override heuristics when validation is ambiguous
    if not validation.get("passed") and revision_count < max_revisions:
        try:
            llm = get_llm_for_agent(agent_name)
            structured = llm.with_structured_output(OrchestratorDecision, method="function_calling")
            prompt = get_prompt(agent_name)
            messages = [
                SystemMessage(content=prompt),
                HumanMessage(
                    content=(
                        f"Validation: {validation}\n"
                        f"Detail score: {detail_score:.2f}\n"
                        f"Revision count: {revision_count}, enrich count: {enrich_count}\n"
                        f"Heuristic suggestion: {decision.next_action}\n"
                        "Choose next_action: enrich | rebuild | gather | book"
                    )
                ),
            ]
            llm_decision: OrchestratorDecision = await structured.ainvoke(messages)
            action_map = {
                "enrich": "itinerary_enrich_node",
                "rebuild": "itinerary_node",
                "book": "booking_node",
            }
            if llm_decision.next_action in action_map:
                goto = action_map[llm_decision.next_action]
                decision = llm_decision
                update["orchestrator_decision"] = decision.model_dump()
                if goto == "itinerary_enrich_node":
                    update["enrich_cycle_count"] = enrich_count + 1
        except Exception:
            pass

    return Command(goto=goto, update=update)
