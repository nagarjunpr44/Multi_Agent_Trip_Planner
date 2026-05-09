from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class Activity(BaseModel):
    name: str
    description: str
    location: str
    duration_minutes: int
    cost_usd: float = 0.0
    category: str = "general"  # sightseeing | food | adventure | culture | transport
    booking_required: bool = False
    booking_url: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class DayPlan(BaseModel):
    day_number: int
    date: str | None = None
    city: str
    theme: str | None = None
    morning: list[Activity] = Field(default_factory=list)
    afternoon: list[Activity] = Field(default_factory=list)
    evening: list[Activity] = Field(default_factory=list)
    travel_between_venues_minutes: int = 0
    day_total_cost_usd: float = 0.0
    notes: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_nulls(cls, values: dict) -> dict:
        for f in ("morning", "afternoon", "evening"):
            if values.get(f) is None:
                values[f] = []
        return values


class Itinerary(BaseModel):
    title: str
    destination: str
    num_days: int
    num_travelers: int
    days: list[DayPlan]
    total_activities_cost_usd: float = 0.0
    highlights: list[str] = Field(default_factory=list)
    travel_tips: list[str] = Field(default_factory=list)
    best_neighborhoods: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_nulls(cls, values: dict) -> dict:
        for f in ("days", "highlights", "travel_tips", "best_neighborhoods"):
            if values.get(f) is None:
                values[f] = []
        return values


class Experience(BaseModel):
    name: str
    category: str  # restaurant | attraction | hidden_gem | activity
    address: str
    city: str
    rating: float | None = None
    num_reviews: int | None = None
    price_level: int | None = Field(None, ge=1, le=4)
    description: str
    cuisine_type: str | None = None
    opening_hours: str | None = None
    foursquare_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
