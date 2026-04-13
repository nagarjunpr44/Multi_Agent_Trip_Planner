from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import httpx
from langchain_core.tools import tool
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import get_settings
from schemas.flight import FlightOption, FlightSearchParams, FlightSearchResult, FlightSegment



@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
async def _search_serpapi_flights(params: FlightSearchParams) -> FlightSearchResult:
    s = get_settings()
    api_key = s.apis.serpapi_api_key
    
    # Class mapping for Serpapi
    class_map = {
        "ECONOMY": 1,
        "PREMIUM_ECONOMY": 2,
        "BUSINESS": 3,
        "FIRST": 4
    }
    travel_class = class_map.get(params.travel_class.upper(), 1)
    
    q_params = {
        "engine": "google_flights",
        "departure_id": params.origin,
        "arrival_id": params.destination,
        "outbound_date": params.departure_date,
        "currency": "USD",
        "adults": params.num_adults,
        "travel_class": travel_class,
        "api_key": api_key,
    }
    
    if params.return_date:
        q_params["return_date"] = params.return_date
        q_params["type"] = 1 # Round trip
    else:
        q_params["type"] = 2 # One way
        
    async with httpx.AsyncClient() as client:
        response = await client.get("https://serpapi.com/search", params=q_params, timeout=s.app.tool_timeout_seconds)
        response.raise_for_status()
        data = response.json()
        
    options = []
    
    # Try fetching best_flights, then other_flights
    raw_flights = data.get("best_flights", []) + data.get("other_flights", [])
    
    for i, flight in enumerate(raw_flights[:params.max_results]):
        try:
            segments_data = flight.get("flights", [])
            all_segments = []
            
            for seg in segments_data:
                dep_time_str = seg.get("departure_airport", {}).get("time", "")
                arr_time_str = seg.get("arrival_airport", {}).get("time", "")
                
                # Serpapi times format: "2026-04-12 10:00"
                # If there's no year, fallback to just combining
                try:
                    dep_time = datetime.strptime(dep_time_str, "%Y-%m-%d %H:%M")
                except:
                    dep_time = datetime.strptime(f"{params.departure_date} {dep_time_str.split(' ')[-1]}", "%Y-%m-%d %H:%M")
                    
                try:
                    arr_time = datetime.strptime(arr_time_str, "%Y-%m-%d %H:%M")
                except:
                    arr_time = datetime.strptime(f"{params.departure_date} {arr_time_str.split(' ')[-1]}", "%Y-%m-%d %H:%M")
                
                all_segments.append(
                    FlightSegment(
                        departure_airport=seg.get("departure_airport", {}).get("id", params.origin),
                        arrival_airport=seg.get("arrival_airport", {}).get("id", params.destination),
                        departure_time=dep_time,
                        arrival_time=arr_time,
                        carrier_code=seg.get("airline", "Unknown")[:2].upper(),
                        flight_number=seg.get("flight_number", "000"),
                        duration_minutes=seg.get("duration", 0),
                        cabin_class=params.travel_class,
                    )
                )
            
            price = flight.get("price", 0.0)
            if not isinstance(price, (int, float)):
                # Clean "$500" strings just in case
                import re
                prices = re.findall(r"\d+", str(price))
                price = float(prices[0]) if prices else 0.0
                
            options.append(
                FlightOption(
                    id=flight.get("booking_token", f"serp-{i}"),
                    segments=all_segments,
                    total_duration_minutes=flight.get("total_duration", 0),
                    num_stops=len(all_segments) - 1,
                    price_usd=float(price),
                    airline=flight.get("airline", "Multiple Airlines") or "Multiple Airlines",
                    booking_url=data.get("search_metadata", {}).get("google_flights_url", ""),
                    is_refundable=False,
                )
            )
        except Exception as e:
            continue

    options.sort(key=lambda x: x.price_usd)
    return FlightSearchResult(
        params=params,
        options=options,
        cheapest_usd=options[0].price_usd if options else None,
        fastest_minutes=min(o.total_duration_minutes for o in options) if options else None,
        source="serpapi",
        is_mock=False,
    )


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
    """Search for flight options between two airports using Google Flights via SerpApi.

    Args:
        origin: IATA airport code (e.g. JFK, LAX, LHR)
        destination: IATA airport code (e.g. NRT, CDG, SYD)
        departure_date: Departure date in YYYY-MM-DD format
        return_date: Return date in YYYY-MM-DD format (empty for one-way)
        num_adults: Number of adult passengers
        travel_class: ECONOMY | PREMIUM_ECONOMY | BUSINESS | FIRST
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
    if not s.apis.serpapi_api_key:
        return json.dumps({"error": "SERPAPI_API_KEY is not configured. Cannot search flights."})
        
    result = await _search_serpapi_flights(params)

    return result.model_dump_json()
