from __future__ import annotations

from pydantic import BaseModel, Field


class HotelAmenity(BaseModel):
    name: str
    category: str = "general"


class HotelOption(BaseModel):
    id: str
    name: str
    address: str
    city: str
    country: str
    star_rating: int = Field(ge=1, le=5)
    price_per_night_usd: float
    total_price_usd: float
    num_nights: int
    check_in: str
    check_out: str
    amenities: list[HotelAmenity] = Field(default_factory=list)
    rating_score: float | None = None
    num_reviews: int | None = None
    booking_url: str | None = None
    is_refundable: bool = False
    latitude: float | None = None
    longitude: float | None = None
    image_url: str | None = None


class HotelSearchParams(BaseModel):
    city_code: str = Field(..., description="IATA city code, e.g. TYO")
    check_in: str = Field(..., description="YYYY-MM-DD")
    check_out: str = Field(..., description="YYYY-MM-DD")
    num_adults: int = 1
    star_rating_min: int | None = None
    budget_per_night_max_usd: float | None = None
    max_results: int = 5


class HotelSearchResult(BaseModel):
    params: HotelSearchParams
    options: list[HotelOption]
    cheapest_per_night_usd: float | None = None
    source: str = "amadeus"
    is_mock: bool = False
