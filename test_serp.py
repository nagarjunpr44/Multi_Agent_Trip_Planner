import asyncio
from datetime import date, timedelta

import httpx

from config.settings import get_settings


async def main():
    s = get_settings()
    if not s.apis.serpapi_api_key:
        raise RuntimeError("SERPAPI_API_KEY is not configured")

    outbound = date.today() + timedelta(days=60)
    inbound = outbound + timedelta(days=3)
    params = {
        "engine": "google_flights",
        "departure_id": "BER",
        "arrival_id": "CDG",
        "outbound_date": outbound.isoformat(),
        "return_date": inbound.isoformat(),
        "currency": "USD",
        "adults": 1,
        "type": 1,
        "api_key": s.apis.serpapi_api_key,
    }

    async with httpx.AsyncClient() as client:
        response = await client.get("https://serpapi.com/search", params=params, timeout=30)
        print("Flights Status:", response.status_code)
        print("Flights Text:", response.text[:2000])


if __name__ == "__main__":
    asyncio.run(main())
