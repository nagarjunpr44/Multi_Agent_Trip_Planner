from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FlightSegment(BaseModel):
    departure_airport: str
    arrival_airport: str
    departure_time: datetime
    arrival_time: datetime
    carrier_code: str
    flight_number: str
    duration_minutes: int
    cabin_class: str = "ECONOMY"


class FlightOption(BaseModel):
    id: str
    segments: list[FlightSegment]
    total_duration_minutes: int
    num_stops: int
    price_usd: float
    currency: str = "USD"
    airline: str
    booking_url: str | None = None
    is_refundable: bool = False
    baggage_included: bool = False


class FlightSearchParams(BaseModel):
    origin: str = Field(..., description="IATA airport code, e.g. JFK")
    destination: str = Field(..., description="IATA airport code, e.g. NRT")
    departure_date: str = Field(..., description="YYYY-MM-DD")
    return_date: str | None = Field(None, description="YYYY-MM-DD for round-trip")
    num_adults: int = 1
    travel_class: str = "ECONOMY"
    max_results: int = 5


class FlightSearchResult(BaseModel):
    params: FlightSearchParams
    options: list[FlightOption]
    cheapest_usd: float | None = None
    fastest_minutes: int | None = None
    source: str = "amadeus"
    is_mock: bool = False
