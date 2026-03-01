from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

from schemas.budget import BudgetAnalysis
from schemas.flight import FlightSearchResult
from schemas.hotel import HotelSearchResult
from schemas.itinerary import Experience, Itinerary


class ToolError(BaseModel):
    tool_name: str
    error_code: str
    message: str
    is_recoverable: bool = True


class SupervisorPlan(BaseModel):
    """Structured output from the Supervisor agent."""

    destination_summary: str = ""
    execution_plan: list[str] = Field(default_factory=list)
    parallel_targets: list[str] = Field(default_factory=list)
    constraints_parsed: dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""

    @model_validator(mode="before")
    @classmethod
    def _coerce_nulls(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for f in ("execution_plan", "parallel_targets"):
                if data.get(f) is None:
                    data[f] = []
        return data


class DestinationInfo(BaseModel):
    """Structured output from the Research agent."""

    destination: str = ""
    country: str = ""
    region: str = ""
    best_months_to_visit: list[str] = Field(default_factory=list)
    current_weather_summary: str = ""
    upcoming_events: list[str] = Field(default_factory=list)
    visa_requirements: Optional[str] = None
    safety_notes: Optional[str] = None
    cultural_tips: list[str] = Field(default_factory=list)
    language: Optional[str] = None
    currency: Optional[str] = None
    timezone: Optional[str] = None
    highlights: list[str] = Field(default_factory=list)
    local_tips: list[str] = Field(default_factory=list)
    best_season: Optional[str] = None
    research_sources: list[str] = Field(default_factory=list)
    city: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_nulls(cls, data: Any) -> Any:
        if isinstance(data, dict):
            list_fields = (
                "best_months_to_visit", "upcoming_events", "cultural_tips",
                "research_sources", "highlights", "local_tips",
            )
            for f in list_fields:
                if data.get(f) is None:
                    data[f] = []
            # Populate city from destination if missing
            if not data.get("city") and data.get("destination"):
                data["city"] = data["destination"]
        return data


class ValidationResult(BaseModel):
    """Structured output from the Validator agent."""

    score: float = Field(default=0.0, ge=0.0, le=1.0)
    passed: bool = False
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    feasibility_score: float = Field(default=1.0, ge=0.0, le=1.0)
    budget_alignment_score: float = Field(default=1.0, ge=0.0, le=1.0)
    coverage_score: float = Field(default=1.0, ge=0.0, le=1.0)
    quality_score: float = Field(default=1.0, ge=0.0, le=1.0)

    @model_validator(mode="before")
    @classmethod
    def _coerce_nulls(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for f in ("issues", "suggestions"):
                if data.get(f) is None:
                    data[f] = []
        return data


class BookingResult(BaseModel):
    """Structured output from the Booking agent."""

    booking_reference: Optional[str] = None
    flight_booking: Optional[dict] = None
    hotel_booking: Optional[dict] = None
    total_charged_usd: float = 0.0
    confirmation_details: Optional[str] = None
    booked_at: Optional[str] = None
    status: str = "confirmed"  # pending | confirmed | failed | skipped

    @model_validator(mode="before")
    @classmethod
    def _coerce_booking_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # LLM sometimes returns a booking-reference string instead of a dict
            for f in ("flight_booking", "hotel_booking"):
                val = data.get(f)
                if isinstance(val, str):
                    data[f] = {"reference": val}
        return data


class AgentOutput(BaseModel):
    """Generic envelope for any agent's output stored in state."""

    agent_name: str
    success: bool
    data: Optional[dict] = None
    error: Optional[ToolError] = None
    duration_ms: Optional[int] = None
