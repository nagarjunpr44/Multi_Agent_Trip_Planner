from __future__ import annotations

from langchain_core.tools import tool
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import get_settings
from schemas.hotel import HotelAmenity, HotelOption, HotelSearchParams, HotelSearchResult


def _mock_hotels(params: HotelSearchParams) -> HotelSearchResult:
    import random
    nights = _count_nights(params.check_in, params.check_out)
    tiers = [
        ("Budget Inn Central", 1, 2, 65.0),
        ("Comfort Stay Hotel", 3, 3, 120.0),
        ("Grand Metropolitan", 4, 4, 210.0),
        ("Luxury Palace Suites", 5, 5, 380.0),
        ("Boutique Stay & Co", 3, 4, 155.0),
    ]
    options = []
    for i, (name, stars, rating, ppn) in enumerate(tiers[: params.max_results]):
        total = round(ppn * nights, 2)
        options.append(
            HotelOption(
                id=f"MOCK-HTL-{i:03d}",
                name=name,
                address=f"{100 + i * 10} Main Street",
                city=params.city_code,
                country="N/A",
                star_rating=stars,
                price_per_night_usd=ppn,
                total_price_usd=total,
                num_nights=nights,
                check_in=params.check_in,
                check_out=params.check_out,
                amenities=[
                    HotelAmenity(name="WiFi", category="connectivity"),
                    HotelAmenity(name="Breakfast", category="dining"),
                ],
                rating_score=float(rating),
                is_refundable=i % 2 == 0,
            )
        )
    options.sort(key=lambda x: x.price_per_night_usd)
    return HotelSearchResult(
        params=params,
        options=options,
        cheapest_per_night_usd=options[0].price_per_night_usd,
        source="mock",
        is_mock=True,
    )


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
async def _search_amadeus_hotels(params: HotelSearchParams) -> HotelSearchResult:
    from amadeus import Client
    s = get_settings()
    amadeus = Client(
        client_id=s.apis.amadeus_api_key,
        client_secret=s.apis.amadeus_api_secret,
        hostname=s.apis.amadeus_hostname,
    )
    nights = _count_nights(params.check_in, params.check_out)

    # Step 1: Get hotel list for city
    hotel_list = amadeus.reference_data.locations.hotels.by_city.get(
        cityCode=params.city_code
    )
    hotel_ids = [h["hotelId"] for h in (hotel_list.data or [])[:20]]
    if not hotel_ids:
        return _mock_hotels(params)

    # Step 2: Get offers
    offers_response = amadeus.shopping.hotel_offers_search.get(
        hotelIds=",".join(hotel_ids[:10]),
        checkInDate=params.check_in,
        checkOutDate=params.check_out,
        adults=params.num_adults,
        currencyCode="USD",
        bestRateOnly=True,
    )
    raw = offers_response.data or []
    options = []
    for item in raw[: params.max_results]:
        try:
            hotel = item.get("hotel", {})
            offer = item.get("offers", [{}])[0]
            ppn = float(offer.get("price", {}).get("base", 0))
            amenities_raw = hotel.get("amenities", [])
            options.append(
                HotelOption(
                    id=item.get("hotel", {}).get("hotelId", ""),
                    name=hotel.get("name", "Unknown Hotel"),
                    address=hotel.get("address", {}).get("lines", [""])[0],
                    city=hotel.get("address", {}).get("cityName", params.city_code),
                    country=hotel.get("address", {}).get("countryCode", ""),
                    star_rating=int(hotel.get("rating", 3)),
                    price_per_night_usd=ppn,
                    total_price_usd=round(ppn * nights, 2),
                    num_nights=nights,
                    check_in=params.check_in,
                    check_out=params.check_out,
                    amenities=[HotelAmenity(name=a) for a in amenities_raw[:5]],
                    latitude=hotel.get("latitude"),
                    longitude=hotel.get("longitude"),
                )
            )
        except Exception:
            continue

    options.sort(key=lambda x: x.price_per_night_usd)
    return HotelSearchResult(
        params=params,
        options=options,
        cheapest_per_night_usd=options[0].price_per_night_usd if options else None,
        source="amadeus",
        is_mock=False,
    )


@tool
async def search_hotels_tool(
    city_code: str,
    check_in: str,
    check_out: str,
    num_adults: int = 1,
    star_rating_min: int = 0,
    budget_per_night_max_usd: float = 0.0,
    max_results: int = 5,
) -> str:
    """Search for hotel accommodations in a city.

    Args:
        city_code: IATA city code (e.g. TYO, PAR, LON, NYC)
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
        city_code=city_code.upper(),
        check_in=check_in,
        check_out=check_out,
        num_adults=num_adults,
        star_rating_min=star_rating_min if star_rating_min > 0 else None,
        budget_per_night_max_usd=budget_per_night_max_usd if budget_per_night_max_usd > 0 else None,
        max_results=max_results,
    )
    s = get_settings()
    if s.app.mock_fallback or not s.apis.amadeus_api_key:
        result = _mock_hotels(params)
    else:
        try:
            result = await _search_amadeus_hotels(params)
        except Exception as exc:
            result = _mock_hotels(params)
            result.source = f"mock_fallback:{type(exc).__name__}"
            result.is_mock = True

    return result.model_dump_json()
