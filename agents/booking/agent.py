from __future__ import annotations

import time
from datetime import date, datetime

from agents.llm_factory import get_llm_for_agent
from agents.state import TravelState
from prompts.loader import get_prompt
from schemas.agent_output import BookingResult


async def booking_node(state: TravelState) -> dict:
    """
    Booking Agent — produces a Trip Booking Package from real provider search data.

    Autonomous mode:   builds package immediately and generates a human-readable summary.
    HITL mode:         graph pauses at interrupt_before=["booking_node"];
                       node runs only after the user resumes via API with human_approved=True.

    Status values (honest):
      ready_to_book     — real prices calculated, actionable next steps provided
      awaiting_approval — HITL mode, paused for human review
      skipped           — booking step deliberately skipped

    is_real_booking is always False until Duffel/LiteAPI live-booking integration is added.
    """
    t0 = time.monotonic()
    agent_name = "booking"

    llm = get_llm_for_agent(agent_name)
    system_prompt = get_prompt(agent_name)

    human_approved = state.get("human_approved", False)
    mode = state.get("mode", "autonomous")
    human_feedback = state.get("human_feedback")
    session_id = state.get("session_id", "00000000")

    # HITL guard: graph interrupts before this node, but defensive check
    if mode == "hitl" and not human_approved:
        return {
            "status": "awaiting_approval",
            "booking_result": BookingResult(status="awaiting_approval").model_dump(),
        }

    constraints = state.get("constraints", {})
    flight_results = state.get("flight_results") or {}
    hotel_results = state.get("hotel_results") or {}
    budget_analysis = state.get("budget_analysis") or {}

    # Step 1: Build the trip booking package from real search data (no LLM)
    package = _build_booking_package(
        constraints, flight_results, hotel_results, budget_analysis, session_id
    )

    budget_usd = constraints.get("budget_usd")
    status = "ready_to_book"
    if budget_usd and package["total_estimated_usd"] > float(budget_usd):
        status = "budget_exceeded"

    # Step 2: LLM writes human-readable summary grounded in real package data
    summary = await _generate_summary(
        llm, system_prompt, package, constraints, human_feedback, status
    )

    result = BookingResult(
        booking_reference=package["booking_reference"],
        status=status,
        flight_offer_id=package.get("flight_offer_id"),
        flight_booking=package.get("flight_booking"),
        hotel_offer_id=package.get("hotel_offer_id"),
        hotel_booking=package.get("hotel_booking"),
        total_estimated_usd=package["total_estimated_usd"],
        price_breakdown=package["price_breakdown"],
        booking_instructions=package["booking_instructions"],
        booking_links=package.get("booking_links", {}),
        summary=summary,
        booked_at=datetime.utcnow().isoformat(),
        is_real_booking=False,
    )

    duration_ms = round((time.monotonic() - t0) * 1000)
    timings = dict(state.get("agent_timings", {}))
    timings[agent_name] = duration_ms

    return {
        "booking_result": result.model_dump(),
        "status": "completed",
        "agent_timings": timings,
    }


def _build_booking_package(
    constraints: dict,
    flight_results: dict,
    hotel_results: dict,
    budget_analysis: dict,
    session_id: str,
) -> dict:
    """
    Extracts real provider offer IDs and prices from search results, calculates the
    true total cost, and produces actionable booking instructions.

    No LLM is used here — all data comes from real API responses already in state.
    """
    sel_flight = (flight_results.get("options") or [{}])[0]
    sel_hotel = (hotel_results.get("options") or [{}])[0]

    flight_total = float(sel_flight.get("price_usd") or 0)
    nights = _calc_nights(constraints)
    ppn = float(sel_hotel.get("price_per_night_usd") or 0)
    hotel_total = ppn * nights
    mid = budget_analysis.get("mid") or {}
    activities_est = float(mid.get("activities_usd") or 0)
    food_est = float(mid.get("food_usd") or 0)
    transport_est = float(mid.get("transport_usd") or 0)
    misc_est = float(mid.get("misc_usd") or 0)
    total = flight_total + hotel_total + activities_est + food_est + transport_est + misc_est

    ref = f"TRIP-{str(session_id)[:8].upper()}"

    destination = constraints.get("destination") or (
        constraints.get("destinations") or ["Unknown"]
    )[0]
    dep = constraints.get("departure_date", "TBD")
    ret = constraints.get("return_date", "TBD")
    airline = sel_flight.get("airline", "N/A")
    hotel_name = sel_hotel.get("name", "N/A")
    flight_offer_id = sel_flight.get("offer_id") or sel_flight.get("id")
    hotel_offer_id = sel_hotel.get("offer_id") or sel_hotel.get("id")

    booking_instructions = [
        f"FLIGHT: {airline} — {dep} → {ret} for {destination}",
        f"  Price: ${flight_total:.2f} total per booking",
        (
            f"  Provider Offer ID: {flight_offer_id} (verify before checkout)"
            if flight_offer_id
            else "  Search directly on airline website or a travel portal (e.g., Google Flights)"
        ),
        "",
        f"HOTEL: {hotel_name} — {nights} night(s) @ ${ppn:.2f}/night = ${hotel_total:.2f}",
        (
            f"  Provider Offer ID: {hotel_offer_id} (verify before checkout)"
            if hotel_offer_id
            else "  Book directly on hotel website or booking.com"
        ),
        "",
        "NEXT STEPS TO COMPLETE BOOKING:",
        "  1. Verify flight availability and price on airline website or Google Flights",
        "  2. Book flight and request confirmation email",
        "  3. Verify hotel availability on hotel website or booking.com",
        "  4. Book hotel and request confirmation email",
        "  5. Check visa requirements for your nationality (see destination research notes)",
        "",
        (
            "LIVE BOOKING (future): integrate Duffel API (flights) + LiteAPI "
            "(hotels) to book in one click."
        ),
    ]

    return {
        "booking_reference": ref,
        "flight_offer_id": flight_offer_id,
        "hotel_offer_id": hotel_offer_id,
        "flight_booking": sel_flight if sel_flight else None,
        "hotel_booking": sel_hotel if sel_hotel else None,
        "total_estimated_usd": round(total, 2),
        "price_breakdown": {
            "flights_usd": round(flight_total, 2),
            "hotel_usd": round(hotel_total, 2),
            "activities_usd": round(activities_est, 2),
            "food_usd": round(food_est, 2),
            "transport_usd": round(transport_est, 2),
            "misc_usd": round(misc_est, 2),
        },
        "booking_instructions": [line for line in booking_instructions],
        "booking_links": {},
    }


async def _generate_summary(
    llm: object,
    system_prompt: str,
    package: dict,
    constraints: dict,
    human_feedback: str | None,
    status: str = "ready_to_book",
) -> str:
    """LLM generates a 2-3 sentence human-readable trip summary from real package data."""
    destination = constraints.get("destination") or (
        constraints.get("destinations") or ["your destination"]
    )[0]
    dep = constraints.get("departure_date", "TBD")
    ret = constraints.get("return_date", "TBD")
    ref = package["booking_reference"]
    total = package["total_estimated_usd"]
    breakdown = package["price_breakdown"]

    feedback_note = (
        f"\nUser modification request: {human_feedback}\nIncorporate this into the summary."
        if human_feedback
        else ""
    )

    prompt = (
        f"Write a concise 2-3 sentence trip booking summary for the user. "
        f"Use ONLY the real data below — do NOT say 'confirmed' or 'booked', "
        f"as this is a pre-booking plan awaiting user action.\n\n"
        f"Trip reference: {ref}\n"
        f"Destination: {destination}\n"
        f"Dates: {dep} → {ret}\n"
        f"Total estimated cost: ${total:.2f}\n"
        f"Breakdown: flights ${breakdown.get('flights_usd', 0):.2f}, "
        f"hotel ${breakdown.get('hotel_usd', 0):.2f}, "
        f"activities ${breakdown.get('activities_usd', 0):.2f}\n"
        f"Status: {status}\n"
    )

    if status == "budget_exceeded":
        budget_usd = constraints.get("budget_usd", 0)
        prompt += (
            f"\nCRITICAL: The total cost (${total:.2f}) exceeds the user's budget "
            f"of ${budget_usd}! You MUST write a polite negotiation message. "
            "Provide proof by explicitly stating the cost of the flights "
            f"(${breakdown.get('flights_usd', 0):.2f}) and hotels "
            f"(${breakdown.get('hotel_usd', 0):.2f}) that we found in real-time. "
            "Give them strong reasons why the budget is impossible, and offer "
            "two explicit options: 1) Reduce the number of nights, or "
            "2) Increase their budget. "
        )
    else:
        prompt += "Status: Ready to book — awaiting your action to complete reservations.\n"

    prompt += feedback_note

    from langchain_core.messages import HumanMessage as HM
    from langchain_core.messages import SystemMessage as SM

    response = await llm.ainvoke([SM(content=system_prompt), HM(content=prompt)])  # type: ignore[union-attr]
    return str(response.content) if response else ""


def _calc_nights(constraints: dict) -> int:
    """Calculate trip duration in nights from departure and return dates."""
    dep_str = constraints.get("departure_date")
    ret_str = constraints.get("return_date")
    if dep_str and ret_str:
        try:
            return max(1, (date.fromisoformat(ret_str) - date.fromisoformat(dep_str)).days)
        except ValueError:
            pass
    return 1
