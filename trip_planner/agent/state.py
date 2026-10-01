"""Graph state: the conversation plus the Trip document and search results."""

from __future__ import annotations

from langgraph.graph import MessagesState


class PlannerState(MessagesState):
    trip: dict  # Trip.model_dump(mode="json")
    flight_options: dict[str, dict]  # option id → FlightOption dump
    hotel_options: dict[str, dict]  # option id → HotelOption dump
    places: dict[str, dict]  # place_id → Place dump
    user_id: str
