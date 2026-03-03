from __future__ import annotations

import time

from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm_factory import get_llm_for_agent
from agents.state import TravelState
from prompts.loader import get_prompt
from schemas.agent_output import SupervisorPlan


async def supervisor_node(state: TravelState) -> dict:
    """
    Supervisor node: parses user query, produces execution plan.
    Uses structured output to return a SupervisorPlan.
    """
    t0 = time.monotonic()

    llm = get_llm_for_agent("supervisor")
    structured_llm = llm.with_structured_output(SupervisorPlan, method="function_calling")

    system_prompt = get_prompt("supervisor")
    constraints = state.get("constraints", {})
    context = state.get("user_context", {}) or {}
    past_trips = context.get("past_trips", [])
    memory_note = ""
    if past_trips:
        memory_note = "\n\nUser's past trips for context:\n" + "\n".join(
            f"- {t}" for t in past_trips[:2]
        )

    messages = [
        SystemMessage(content=system_prompt + memory_note),
        HumanMessage(
            content=(
                f"User request: {state['user_query']}\n\n"
                f"Constraints: {constraints}"
            )
        ),
    ]

    plan: SupervisorPlan = await structured_llm.ainvoke(messages)
    duration_ms = round((time.monotonic() - t0) * 1000)

    timings = dict(state.get("agent_timings", {}))
    timings["supervisor"] = duration_ms

    return {
        "execution_plan": plan.execution_plan,
        "parallel_targets": plan.parallel_targets,
        "supervisor_plan": plan.model_dump(),
        "status": "running",
        "agent_timings": timings,
    }
