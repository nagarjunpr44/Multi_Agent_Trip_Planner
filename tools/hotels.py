from __future__ import annotations

import json
from typing import Any

import httpx
from langchain_core.tools import tool
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import get_settings
from schemas.hotel import HotelAmenity, HotelOption, HotelSearchParams, HotelSearchResult


def _count_nights(check_in: str, check_out: str) -> int:
    from datetime import date

    ci = date.fromisoformat(check_in)
    co = date.fromisoformat(check_out)
    return max(1, (co - ci).days)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
async def _search_serpapi_hotels(params: HotelSearchParams) -> HotelSearchResult:
    s = get_settings()
    nights = _count_nights(params.check_in, params.check_out)

    q_params: dict[str, Any] = {
        "engine": "google_hotels",
        "q": params.city_code,  # SerpApi handles City names or codes well in 'q'
        "check_in_date": params.check_in,
        "check_out_date": params.check_out,
        "adults": params.num_adults,
        "currency": "USD",
        "api_key": s.apis.serpapi_api_key,
    }

    # Optional filters
    if params.star_rating_min and params.star_rating_min > 0:
        q_params["hotel_classes"] = params.star_rating_min

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://serpapi.com/search",
            params=q_params,
            timeout=s.app.tool_timeout_seconds,
        )
        try:
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError:
            return HotelSearchResult(
                params=params, options=[], source="serpapi_error", is_mock=False
            )

    raw_properties = data.get("properties", [])
    options = []

    for i, prop in enumerate(raw_properties[:params.max_results]):
        try:
            ppn = prop.get("rate_per_night", {}).get("extracted_lowest", 0.0)
            if ppn == 0.0:
                continue

            # Filter by budget if provided
            if params.budget_per_night_max_usd and ppn > params.budget_per_night_max_usd:
                continue

            amenities_raw = prop.get("amenities", [])
            amenities = []
            for a in amenities_raw[:5]:
                if isinstance(a, str):
                    amenities.append(HotelAmenity(name=a))
                elif isinstance(a, dict) and "amenity" in a:
                    amenities.append(HotelAmenity(name=a["amenity"]))

            options.append(
                HotelOption(
                    id=prop.get("property_token", f"htl-{i}"),
                    name=prop.get("name", "Unknown Hotel"),
                    address=prop.get("description", "Address not provided")[:100],
                    city=params.city_code,
                    country="Unknown",
                    star_rating=int(prop.get("hotel_class", params.star_rating_min or 3)),
                    price_per_night_usd=float(ppn),
                    total_price_usd=prop.get("total_rate", {}).get(
                        "extracted_lowest", round(ppn * nights, 2)
                    ),
                    num_nights=nights,
                    check_in=params.check_in,
                    check_out=params.check_out,
                    amenities=amenities,
                    rating_score=float(prop.get("overall_rating", 0.0)),
                    num_reviews=int(prop.get("reviews", 0)),
                    booking_url=prop.get("link", ""),
                    latitude=prop.get("gps_coordinates", {}).get("latitude"),
                    longitude=prop.get("gps_coordinates", {}).get("longitude"),
                    image_url=(
                        prop.get("images", [{"thumbnail": ""}])[0].get("thumbnail")
                        if prop.get("images")
                        else None
                    ),
                )
            )
        except Exception:
            continue

    options.sort(key=lambda x: x.price_per_night_usd)
    return HotelSearchResult(
        params=params,
        options=options,
        cheapest_per_night_usd=options[0].price_per_night_usd if options else None,
        source="serpapi",
        is_mock=False,
    )


@tool
async def search_hotels_tool(
    city: str,
    check_in: str,
    check_out: str,
    num_adults: int = 1,
    star_rating_min: int = 0,
    budget_per_night_max_usd: float = 0.0,
    max_results: int = 5,
) -> str:
    """Search for hotel accommodations in a city using Google Hotels via SerpApi.

    Args:
        city: IATA city code or city name (e.g. TYO, Paris, NYC)
        check_in: Check-in date YYYY-MM-DD
        check_out: Check-out date YYYY-MM-DD
        num_adults: Number of adult guests
        star_rating_min: Minimum star rating (0 = no filter)
        budget_per_night_max_usd: Max budget per night in USD (0 = no filter)
        max_results: Maximum number of hotel options

    Returns:
        JSON string of HotelSearchResult
    """
    params = HotelSearchParams(
        city_code=city.upper(),
        check_in=check_in,
        check_out=check_out,
        num_adults=num_adults,
        star_rating_min=star_rating_min if star_rating_min > 0 else None,
        budget_per_night_max_usd=budget_per_night_max_usd if budget_per_night_max_usd > 0 else None,
        max_results=max_results,
    )
    s = get_settings()
    if not s.apis.serpapi_api_key:
        return json.dumps({"error": "SERPAPI_API_KEY is not configured. Cannot search hotels."})
        
    result = await _search_serpapi_hotels(params)

    return result.model_dump_json()
