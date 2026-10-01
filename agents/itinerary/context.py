from __future__ import annotations

from agents.state import TravelState


def build_itinerary_context(
    state: TravelState,
    num_days: int,
    num_travelers: int,
    destination: str,
    day_labels: list[str],
) -> str:
    """Assemble full trip context for itinerary and enrich agents."""
    dest_info = state.get("destination_info") or {}
    budget_analysis = state.get("budget_analysis") or {}
    flight_results = state.get("flight_results") or {}
    hotel_results = state.get("hotel_results") or {}
    experiences = state.get("experience_results") or []

    flight_info = "No flight data."
    if flight_results.get("options"):
        fo = flight_results["options"][0]
        flight_info = (
            f"Selected flight: {fo.get('airline', 'N/A')} | "
            f"${fo.get('price_usd', 'N/A')} | "
            f"{fo.get('total_duration_minutes', 'N/A')} min | "
            f"Stops: {fo.get('num_stops', 'N/A')} | "
            f"Booking: {fo.get('booking_url') or 'search airline site'}"
        )

    hotel_info = "No hotel data."
    if hotel_results.get("options"):
        ho = hotel_results["options"][0]
        hotel_info = (
            f"Selected hotel: {ho.get('name', 'N/A')} | "
            f"${ho.get('price_per_night_usd', 'N/A')}/night | "
            f"{ho.get('star_rating', 'N/A')} stars | "
            f"Address: {ho.get('address', 'N/A')} | "
            f"Booking: {ho.get('booking_url') or 'book direct'}"
        )

    exp_lines = []
    for e in experiences:
        line = f"- {e.get('name', 'N/A')}"
        if e.get("address"):
            line += f" | {e['address']}"
        if e.get("rating"):
            line += f" | Rating: {e['rating']}"
        if e.get("category"):
            line += f" | [{e['category']}]"
        if e.get("description"):
            line += f"\n  {e['description'][:300]}"
        exp_lines.append(line)
    exp_info = "\n".join(exp_lines) if exp_lines else "No activity data — use tools to discover POIs."

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
        f"Cultural tips: {', '.join(dest_info.get('cultural_tips', []))}\n"
        f"Weather: {dest_info.get('current_weather_summary', 'N/A')}\n"
        f"Visa: {dest_info.get('visa_requirements', 'N/A')}\n\n"
        f"Flight: {flight_info}\n"
        f"Hotel: {hotel_info}\n\n"
        f"Verified experiences ({len(experiences)}):\n{exp_info}\n\n"
        f"{budget_info}"
    )
