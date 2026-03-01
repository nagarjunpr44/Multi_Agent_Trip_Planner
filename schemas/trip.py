from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class TripConstraints(BaseModel):
    """User-expressed constraints for the trip."""

    model_config = {"extra": "allow"}  # accept UI fields like 'destination'

    budget_usd: Optional[float] = Field(None, description="Total budget in USD")
    budget_tier: Literal["budget", "mid", "luxury"] = "mid"
    departure_date: Optional[date] = None
    return_date: Optional[date] = None
    duration_days: Optional[int] = None
    num_travelers: int = 1
    origin_city: Optional[str] = None
    destinations: list[str] = Field(default_factory=list)
    is_multi_city: bool = False
    preferred_airlines: list[str] = Field(default_factory=list)
    hotel_star_rating: Optional[int] = None
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
    session_id: Optional[str] = Field(
        None, description="Resume existing session if provided"
    )


class TripStatus(str, Enum):
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
    message: Optional[str] = None
    user_query: Optional[str] = None
    constraints: Optional[dict] = None
    itinerary: Optional[dict] = None
    booking: Optional[dict] = None
    raw_state: Optional[dict] = None
    destination_summary: Optional[str] = None
    itinerary_markdown: Optional[str] = None
    total_cost_usd: Optional[float] = None
    flights_summary: Optional[str] = None
    hotels_summary: Optional[str] = None
    experiences_summary: Optional[str] = None
    validation_score: Optional[float] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    errors: list[dict] = Field(default_factory=list)


class HITLResumeRequest(BaseModel):
    approved: bool
    feedback: Optional[str] = None
