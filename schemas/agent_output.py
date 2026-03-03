from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


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
    visa_requirements: str | None = None
    safety_notes: str | None = None
    cultural_tips: list[str] = Field(default_factory=list)
    language: str | None = None
    currency: str | None = None
    timezone: str | None = None
    highlights: list[str] = Field(default_factory=list)
    local_tips: list[str] = Field(default_factory=list)
    best_season: str | None = None
    research_sources: list[str] = Field(default_factory=list)
    city: str | None = None

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
    """
    Trip booking package produced by the Booking agent.

    status values:
      ready_to_book      — plan complete, real prices calculated, awaiting human to book
      awaiting_approval  — HITL mode, paused for human review
      skipped            — booking step deliberately skipped
    """

    # Session-scoped reference (NOT a real airline PNR or hotel confirmation)
    booking_reference: str | None = None
    status: str = "ready_to_book"   # ready_to_book | awaiting_approval | skipped

    # Real flight data sourced from Amadeus search results
    flight_offer_id: str | None = None       # Amadeus offer ID (if available)
    flight_booking: dict | None = None       # full flight option dict from search

    # Real hotel data sourced from Amadeus search results
    hotel_offer_id: str | None = None        # Amadeus offer ID (if available)
    hotel_booking: dict | None = None        # full hotel option dict from search

    # Pricing calculated from real search data (not LLM-estimated)
    total_estimated_usd: float = 0.0
    price_breakdown: dict = Field(default_factory=dict)  # {"flights": x, "hotel": x, ...}

    # Actionable next steps for the human to complete booking
    booking_instructions: list[str] = Field(default_factory=list)
    booking_links: dict = Field(default_factory=dict)    # {"flight": url, "hotel": url}

    # Human-readable summary (LLM-generated from real data)
    summary: str | None = None
    booked_at: str | None = None

    # Flag: False until Duffel/LiteAPI integrated for live booking
    is_real_booking: bool = False

    @model_validator(mode="before")
    @classmethod
    def _coerce_booking_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # LLM sometimes returns a booking-reference string instead of a dict
            for f in ("flight_booking", "hotel_booking"):
                val = data.get(f)
                if isinstance(val, str):
                    data[f] = {"reference": val}
            # Rename legacy total_charged_usd → total_estimated_usd if present
            if "total_charged_usd" in data and "total_estimated_usd" not in data:
                data["total_estimated_usd"] = data.pop("total_charged_usd")
        return data


class AgentOutput(BaseModel):
    """Generic envelope for any agent's output stored in state."""

    agent_name: str
    success: bool
    data: dict | None = None
    error: ToolError | None = None
    duration_ms: int | None = None
