from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class TripConstraints(BaseModel):
    """User-expressed constraints for the trip."""

    model_config = {"extra": "allow"}  # accept UI fields like 'destination'

    budget_usd: float | None = Field(None, description="Total budget in USD")
    budget_tier: Literal["budget", "mid", "luxury"] = "mid"
    departure_date: date | None = None
    return_date: date | None = None
    duration_days: int | None = None
    num_travelers: int = 1
    origin_city: str | None = None
    destinations: list[str] = Field(default_factory=list)
    is_multi_city: bool = False
    preferred_airlines: list[str] = Field(default_factory=list)
    hotel_star_rating: int | None = None
    dietary_restrictions: list[str] = Field(default_factory=list)
    activity_preferences: list[str] = Field(default_factory=list)
    accessibility_needs: bool = False

    @model_validator(mode="before")
    @classmethod
    def _normalise_ui_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # UI sends "destination" (singular); normalise → destinations list
            if "destination" in data and not data.get("destinations"):
                dest = data.pop("destination")
                if dest:
                    data["destinations"] = [dest] if isinstance(dest, str) else dest
            # UI sends "preferences"; normalise → activity_preferences
            if "preferences" in data and not data.get("activity_preferences"):
                data["activity_preferences"] = data.pop("preferences")
        return data


class TripRequest(BaseModel):
    """Incoming request from the user to plan a trip."""

    user_query: str = Field(..., min_length=5, description="Natural-language trip request")
    constraints: TripConstraints = Field(default_factory=TripConstraints)
    mode: Literal["autonomous", "hitl"] = Field(
        default="autonomous",
        description="autonomous = runs to completion; hitl = pauses before booking",
    )
    session_id: str | None = Field(
        None, description="Resume existing session if provided"
    )


class TripStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED_HITL = "paused_hitl"
    COMPLETE = "complete"
    FAILED = "failed"


class TripResponse(BaseModel):
    """Top-level response returned after graph completion."""

    session_id: str
    status: str
    message: str | None = None
    user_query: str | None = None
    constraints: dict | None = None
    itinerary: dict | None = None
    booking: dict | None = None
    raw_state: dict | None = None
    destination_summary: str | None = None
    itinerary_markdown: str | None = None
    total_cost_usd: float | None = None
    flights_summary: str | None = None
    hotels_summary: str | None = None
    experiences_summary: str | None = None
    validation_score: float | None = None
    created_at: str | None = None
    updated_at: str | None = None
    errors: list[dict] = Field(default_factory=list)


class HITLResumeRequest(BaseModel):
    approved: bool | None = None
    feedback: str | None = None
