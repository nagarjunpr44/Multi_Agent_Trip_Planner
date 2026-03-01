from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import get_settings
from schemas.flight import FlightOption, FlightSearchParams, FlightSearchResult, FlightSegment


def _mock_flights(params: FlightSearchParams) -> FlightSearchResult:
    from datetime import datetime, timedelta
    dep = datetime.strptime(params.departure_date, "%Y-%m-%d")
    options = [
        FlightOption(
            id=f"MOCK-FL-00{i}",
            segments=[
                FlightSegment(
                    departure_airport=params.origin,
                    arrival_airport=params.destination,
                    departure_time=dep.replace(hour=6 + i * 4),
                    arrival_time=dep.replace(hour=6 + i * 4) + timedelta(hours=13),
                    carrier_code=["AA", "UA", "DL", "NH", "JL"][i],
                    flight_number=f"{['AA', 'UA', 'DL', 'NH', 'JL'][i]}{100 + i * 37}",
                    duration_minutes=780 + i * 30,
                    cabin_class=params.travel_class,
                )
            ],
            total_duration_minutes=780 + i * 30,
            num_stops=i % 2,
            price_usd=round(450 + i * 120 + (0 if i % 2 == 0 else 80), 2),
            airline=["American Airlines", "United", "Delta", "All Nippon", "Japan Airlines"][i],
            is_refundable=i % 3 == 0,
            baggage_included=i % 2 == 0,
        )
        for i in range(params.max_results)
    ]
    options.sort(key=lambda x: x.price_usd)
    return FlightSearchResult(
        params=params,
        options=options,
        cheapest_usd=options[0].price_usd,
        fastest_minutes=min(o.total_duration_minutes for o in options),
        source="mock",
        is_mock=True,
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
async def _search_amadeus_flights(params: FlightSearchParams) -> FlightSearchResult:
    from amadeus import Client, ResponseError
    s = get_settings()
    amadeus = Client(
        client_id=s.apis.amadeus_api_key,
        client_secret=s.apis.amadeus_api_secret,
        hostname=s.apis.amadeus_hostname,
    )
    kwargs: dict[str, Any] = {
        "originLocationCode": params.origin,
        "destinationLocationCode": params.destination,
        "departureDate": params.departure_date,
        "adults": params.num_adults,
        "travelClass": params.travel_class,
        "max": params.max_results,
        "currencyCode": "USD",
    }
    if params.return_date:
        kwargs["returnDate"] = params.return_date

    response = amadeus.shopping.flight_offers_search.get(**kwargs)
    raw_offers = response.data or []
    options = []
    for offer in raw_offers:
        try:
            itineraries = offer.get("itineraries", [])
            all_segments = []
            total_duration = 0
            for itin in itineraries:
                for seg in itin.get("segments", []):
                    dep_obj = seg["departure"]
                    arr_obj = seg["arrival"]
                    from datetime import datetime as dt
                    all_segments.append(
                        FlightSegment(
                            departure_airport=dep_obj["iataCode"],
                            arrival_airport=arr_obj["iataCode"],
                            departure_time=dt.fromisoformat(dep_obj["at"]),
                            arrival_time=dt.fromisoformat(arr_obj["at"]),
                            carrier_code=seg.get("carrierCode", ""),
                            flight_number=f"{seg.get('carrierCode','')}{seg.get('number','')}",
                            duration_minutes=_parse_duration(itin.get("duration", "PT0H")),
                            cabin_class=params.travel_class,
                        )
                    )
                total_duration += _parse_duration(itin.get("duration", "PT0H"))
            num_stops = max(0, len(all_segments) - 1)
            price = float(offer.get("price", {}).get("grandTotal", 0))
            carrier = offer.get("validatingAirlineCodes", [""])[0]
            options.append(
                FlightOption(
                    id=offer.get("id", ""),
                    segments=all_segments,
                    total_duration_minutes=total_duration,
                    num_stops=num_stops,
                    price_usd=price,
                    airline=carrier,
                )
            )
        except Exception:
            continue

    options.sort(key=lambda x: x.price_usd)
    return FlightSearchResult(
        params=params,
        options=options,
        cheapest_usd=options[0].price_usd if options else None,
        fastest_minutes=min(o.total_duration_minutes for o in options) if options else None,
        source="amadeus",
        is_mock=False,
    )


def _parse_duration(iso: str) -> int:
    """Parse ISO 8601 duration like PT13H45M → minutes."""
    import re
    h = int(re.search(r"(\d+)H", iso).group(1)) if "H" in iso else 0
    m = int(re.search(r"(\d+)M", iso).group(1)) if "M" in iso else 0
    return h * 60 + m


@tool
async def search_flights_tool(
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str = "",
    num_adults: int = 1,
    travel_class: str = "ECONOMY",
    max_results: int = 5,
) -> str:
    """Search for flight options between two airports.

    Args:
        origin: IATA airport code (e.g. JFK, LAX, LHR)
        destination: IATA airport code (e.g. NRT, CDG, SYD)
        departure_date: Departure date in YYYY-MM-DD format
        return_date: Return date in YYYY-MM-DD format (empty for one-way)
        num_adults: Number of adult passengers
        travel_class: ECONOMY | BUSINESS | FIRST
        max_results: Maximum number of options to return

    Returns:
        JSON string of FlightSearchResult
    """
    params = FlightSearchParams(
        origin=origin.upper(),
        destination=destination.upper(),
        departure_date=departure_date,
        return_date=return_date or None,
        num_adults=num_adults,
        travel_class=travel_class,
        max_results=max_results,
    )
    s = get_settings()
    if s.app.mock_fallback or not s.apis.amadeus_api_key:
        result = _mock_flights(params)
    else:
        try:
            result = await _search_amadeus_flights(params)
        except Exception as exc:
            result = _mock_flights(params)
            result.source = f"mock_fallback:{type(exc).__name__}"
            result.is_mock = True

    return result.model_dump_json()
