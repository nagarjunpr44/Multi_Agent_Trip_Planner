from __future__ import annotations

from typing import Optional

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
    rating_score: Optional[float] = None
    num_reviews: Optional[int] = None
    booking_url: Optional[str] = None
    is_refundable: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    image_url: Optional[str] = None


class HotelSearchParams(BaseModel):
    city_code: str = Field(..., description="IATA city code, e.g. TYO")
    check_in: str = Field(..., description="YYYY-MM-DD")
    check_out: str = Field(..., description="YYYY-MM-DD")
    num_adults: int = 1
    star_rating_min: Optional[int] = None
    budget_per_night_max_usd: Optional[float] = None
    max_results: int = 5


class HotelSearchResult(BaseModel):
    params: HotelSearchParams
    options: list[HotelOption]
    cheapest_per_night_usd: Optional[float] = None
    source: str = "amadeus"
    is_mock: bool = False
