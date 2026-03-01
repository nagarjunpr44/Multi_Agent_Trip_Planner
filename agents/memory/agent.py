from __future__ import annotations

import logging

from agents.state import TravelState
from memory.context_manager import ContextManager

logger = logging.getLogger(__name__)

_context_manager = ContextManager()


async def memory_load_node(state: TravelState) -> dict:
    """
    Memory Load Agent — runs at graph START before the supervisor.
    Pulls relevant user-preference context from ChromaDB to enrich planning.
    """
    session_id = state.get("session_id", "")
    user_query = state.get("user_query", "")
    constraints = state.get("constraints", {})

    query_text = (
        f"{user_query} "
        f"destination={constraints.get('destination', '')} "
        f"preferences={','.join(constraints.get('preferences', []))}"
    ).strip()

    user_context: dict = {}
    if session_id and query_text:
        try:
            user_context = await _context_manager.load_user_context(
                user_query=query_text,
                user_id=session_id,
                n_results=5,
            )
        except Exception as exc:  # Non-fatal
            logger.warning("Memory load failed (non-fatal): %s", exc)
            user_context = {}

    logger.info("Memory load complete for session=%s, keys=%s", session_id, list(user_context.keys()))
    return {"user_context": user_context}


async def memory_save_node(state: TravelState) -> dict:
    """
    Memory Save Agent — runs at graph END after booking.
    Embeds the completed trip summary into ChromaDB for future preference retrieval.
    """
    session_id = state.get("session_id", "")
    user_query = state.get("user_query", "")
    constraints = state.get("constraints", {})
    itinerary = state.get("itinerary") or {}
    booking_result = state.get("booking_result") or {}
    validation_result = state.get("validation_result") or {}

    if not session_id:
        return {}

    summary = _build_trip_summary(
        user_query, constraints, itinerary, booking_result, validation_result
    )

    try:
        await _context_manager.save_trip_summary(
            session_id=session_id,
            summary=summary,
            metadata={"trip_id": booking_result.get("booking_reference", session_id)},
        )
        logger.info("Memory saved for session=%s", session_id)
    except Exception as exc:
        logger.warning("Memory save failed (non-fatal): %s", exc)

    return {"status": "completed"}


def _build_trip_summary(
    user_query: str,
    constraints: dict,
    itinerary: dict,
    booking_result: dict,
    validation_result: dict,
) -> str:
    destination = constraints.get("destination", "unknown")
    preferences = constraints.get("preferences", [])
    budget_usd = constraints.get("budget_usd")
    num_travelers = constraints.get("num_travelers", 1)
    num_days = len(itinerary.get("days", []))
    highlights = itinerary.get("highlights", [])[:3]
    score = validation_result.get("score", 0.0)
    status = booking_result.get("status", "unknown")
    total_charged = booking_result.get("total_charged_usd", 0)

    return (
        f"User planned a {num_days}-day trip to {destination} "
        f"for {num_travelers} traveler(s). "
        f"Query: '{user_query}'. "
        f"Preferences: {', '.join(preferences) if preferences else 'none'}. "
        f"Budget: {'$' + str(budget_usd) if budget_usd else 'unspecified'}. "
        f"Highlights: {', '.join(highlights)}. "
        f"Validation score: {score:.2f}. "
        f"Booking status: {status}. "
        f"Total charged: ${total_charged}."
    )
