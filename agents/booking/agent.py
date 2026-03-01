from __future__ import annotations

import time
import uuid
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage

from agents.llm_factory import get_llm_for_agent
from agents.state import TravelState
from prompts.loader import get_prompt
from schemas.agent_output import BookingResult


async def booking_node(state: TravelState) -> dict:
    """
    Booking Agent — HITL interrupt point.

    In autonomous mode:  proceeds directly with mock booking confirmation.
    In HITL mode:        graph pauses at `interrupt_before=["booking_node"]`;
                         the node only runs after the user resumes via the API
                         with `human_approved=True`.

    The node also respects `human_feedback` to modify selections before booking.
    """
    t0 = time.monotonic()
    agent_name = "booking"

    llm = get_llm_for_agent(agent_name)
    structured_llm = llm.with_structured_output(BookingResult, method="function_calling")
    system_prompt = get_prompt(agent_name)

    human_approved = state.get("human_approved", False)
    mode = state.get("mode", "autonomous")
    human_feedback = state.get("human_feedback")

    # In HITL mode and not yet approved — this branch should not normally be
    # reached because the graph interrupts BEFORE this node. Kept as a safety guard.
    if mode == "hitl" and not human_approved:
        return {
            "status": "awaiting_approval",
            "booking_result": None,
        }

    constraints = state.get("constraints", {})
    itinerary = state.get("itinerary") or {}
    flight_results = state.get("flight_results") or {}
    hotel_results = state.get("hotel_results") or {}
    budget_analysis = state.get("budget_analysis") or {}

    booking_prompt = _build_booking_prompt(
        constraints, itinerary, flight_results, hotel_results, budget_analysis, human_feedback
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=booking_prompt),
    ]

    result: BookingResult = await structured_llm.ainvoke(messages)

    # Stamp booking references if LLM left them empty
    if not result.booking_reference:
        result = BookingResult(
            booking_reference=f"ATP-{uuid.uuid4().hex[:8].upper()}",
            flight_booking=result.flight_booking,
            hotel_booking=result.hotel_booking,
            total_charged_usd=result.total_charged_usd,
            confirmation_details=result.confirmation_details,
            booked_at=result.booked_at or datetime.utcnow().isoformat(),
            status=result.status or "confirmed",
        )

    duration_ms = round((time.monotonic() - t0) * 1000)
    timings = dict(state.get("agent_timings", {}))
    timings[agent_name] = duration_ms

    return {
        "booking_result": result.model_dump(),
        "status": "completed",
        "agent_timings": timings,
    }


def _build_booking_prompt(
    constraints: dict,
    itinerary: dict,
    flight_results: dict,
    hotel_results: dict,
    budget_analysis: dict,
    human_feedback: str | None,
) -> str:
    destination = constraints.get("destination", "Unknown")
    departure_date = constraints.get("departure_date", "TBD")
    return_date = constraints.get("return_date", "TBD")
    num_travelers = constraints.get("num_travelers", 1)

    sel_flight = (flight_results.get("options") or [{}])[0]
    sel_hotel = (hotel_results.get("options") or [{}])[0]

    mid_budget = (budget_analysis.get("mid") or {}).get("total_cost_usd", 0)
    breakdown_items = (budget_analysis.get("mid") or {}).get("breakdown", [])
    breakdown_str = "\n".join(
        f"  - {it.get('category', '')}: ${it.get('amount_usd', 0)}"
        for it in breakdown_items[:5]
    ) or "  Not available."

    feedback_section = (
        f"\nUser modifications from HITL review:\n{human_feedback}\n"
        if human_feedback
        else ""
    )

    return (
        f"Process booking for this trip plan:\n\n"
        f"DESTINATION: {destination}\n"
        f"DATES: {departure_date} → {return_date}\n"
        f"TRAVELERS: {num_travelers}\n\n"
        f"SELECTED FLIGHT:\n"
        f"  Airline: {sel_flight.get('airline', 'N/A')}\n"
        f"  Price: ${sel_flight.get('total_price_usd', 'N/A')}\n"
        f"  Duration: {sel_flight.get('duration_minutes', 'N/A')} min\n"
        f"  Class: {sel_flight.get('cabin_class', 'economy')}\n\n"
        f"SELECTED HOTEL:\n"
        f"  Name: {sel_hotel.get('name', 'N/A')}\n"
        f"  Price/night: ${sel_hotel.get('price_per_night_usd', 'N/A')}\n"
        f"  Stars: {sel_hotel.get('star_rating', 'N/A')}\n\n"
        f"ESTIMATED TOTAL COST (mid tier): ${mid_budget}\n"
        f"BUDGET BREAKDOWN:\n{breakdown_str}\n"
        f"{feedback_section}\n"
        "Generate a BookingResult with a mock booking reference, confirmation details, "
        "total charged amount, and status='confirmed'. "
        "This is a simulation — no real payment is processed."
    )
