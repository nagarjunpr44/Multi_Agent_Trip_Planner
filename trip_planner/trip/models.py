"""The Trip document. The planner edits it through tools; code checks it.

Conventions:
- Money is USD. Prices are totals for the whole party unless the name says otherwise.
- Weekdays use Python's convention: Monday=0 … Sunday=6.
- Times are local to the destination.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field


def short_id() -> str:
    return uuid.uuid4().hex[:8]


class OpenPeriod(BaseModel):
    weekday: int = Field(ge=0, le=6)  # Monday=0
    open: time
    close: time  # close <= open means it closes after midnight


class Place(BaseModel):
    place_id: str
    name: str
    address: str = ""
    lat: float | None = None
    lng: float | None = None
    rating: float | None = None
    user_ratings: int | None = None
    price_level: int | None = None  # 0 (free) … 4 (very expensive)
    types: list[str] = Field(default_factory=list)
    hours: list[OpenPeriod] | None = None  # None = unknown; [] = never open
    maps_url: str = ""
    website: str = ""


class FlightOption(BaseModel):
    id: str
    airline: str
    origin: str  # IATA
    destination: str  # IATA
    depart_at: datetime  # outbound departure, local time
    arrive_at: datetime  # outbound arrival, local time
    return_date: date | None = None
    stops: int = 0
    duration_min: int = 0
    price_usd: float  # total for all travelers, round trip if return_date set
    booking_url: str = ""


class HotelOption(BaseModel):
    id: str
    name: str
    address: str = ""
    lat: float | None = None
    lng: float | None = None
    check_in: date
    check_out: date
    price_per_night_usd: float
    total_usd: float
    rating: float | None = None
    stars: int | None = None
    booking_url: str = ""


class Stop(BaseModel):
    id: str = Field(default_factory=short_id)
    place: Place
    start: time
    duration_min: int = Field(gt=0)
    note: str = ""  # why go / tips, written by the planner
    est_cost_usd: float | None = None  # total for the party
    travel_from_prev_min: int | None = None  # filled by code, never the LLM
    travel_mode: Literal["walk", "transit", "drive"] | None = None


class Day(BaseModel):
    date: date
    area: str = ""  # neighborhood the day is built around
    notes: str = ""
    stops: list[Stop] = Field(default_factory=list)


class Trip(BaseModel):
    id: str = Field(default_factory=short_id)
    title: str = ""
    origin: str = ""
    destinations: list[str] = Field(default_factory=list)
    start_date: date | None = None
    end_date: date | None = None
    travelers: int = Field(1, ge=1)
    budget_usd: float | None = None
    tier: Literal["budget", "mid", "luxury"] = "mid"
    pace: Literal["relaxed", "moderate", "packed"] = "moderate"
    prefs: list[str] = Field(default_factory=list)  # "food markets", "art"
    constraints: list[str] = Field(default_factory=list)  # "vegetarian", "no early starts"
    flight: FlightOption | None = None
    hotel: HotelOption | None = None
    days: list[Day] = Field(default_factory=list)
    status: Literal["planning", "awaiting_approval", "approved"] = "planning"
    version: int = 0

    def find_stop(self, stop_id: str) -> tuple[Day, Stop] | None:
        for day in self.days:
            for stop in day.stops:
                if stop.id == stop_id:
                    return day, stop
        return None

    def day_for(self, d: date) -> Day | None:
        return next((day for day in self.days if day.date == d), None)


class Issue(BaseModel):
    """One concrete problem found by check_trip. The planner fixes these one by one."""

    code: str  # e.g. "closed", "overlap", "over_budget", "too_packed", "missing_dates"
    severity: Literal["error", "warning"]
    message: str  # human/LLM readable, e.g. "Day 2: Louvre is closed on Tuesdays"
    date: date | None = None
    stop_id: str | None = None
