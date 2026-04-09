from __future__ import annotations

import httpx
from langchain_core.tools import tool
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import get_settings

OWM_BASE = "https://api.openweathermap.org/data/2.5"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=20),
    reraise=True,
)
async def _fetch_owm_weather(city: str, days: int) -> dict:
    s = get_settings()
    api_key = s.apis.openweathermap_api_key
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Get current weather + geocoding
        geo_resp = await client.get(
            f"{OWM_BASE}/weather",
            params={"q": city, "appid": api_key, "units": "metric"},
        )
        geo_resp.raise_for_status()
        current = geo_resp.json()

        # Get 5-day/3-hour forecast
        forecast_resp = await client.get(
            f"{OWM_BASE}/forecast",
            params={
                "q": city,
                "appid": api_key,
                "units": "metric",
                "cnt": min(days * 8, 40),
            },
        )
        forecast_resp.raise_for_status()
        forecast_data = forecast_resp.json()

    # Aggregate to daily
    daily: dict[str, dict] = {}
    for item in forecast_data.get("list", []):
        day = item["dt_txt"][:10]
        if day not in daily:
            daily[day] = {"highs": [], "lows": [], "conditions": []}
        daily[day]["highs"].append(item["main"]["temp_max"])
        daily[day]["lows"].append(item["main"]["temp_min"])
        daily[day]["conditions"].append(item["weather"][0]["description"])

    forecast = []
    for day, data in list(daily.items())[:days]:
        forecast.append({
            "date": day,
            "condition": data["conditions"][0].title(),
            "temp_high_c": round(max(data["highs"]), 1),
            "temp_low_c": round(min(data["lows"]), 1),
            "humidity_pct": current.get("main", {}).get("humidity", 0),
            "precip_mm": 0.0,
        })

    conditions_str = ", ".join(set(f["condition"] for f in forecast[:3]))
    summary = (
        f"{city}: {conditions_str}. "
        f"Highs around {forecast[0]['temp_high_c']}°C, lows {forecast[0]['temp_low_c']}°C."
        if forecast else f"{city}: Weather data retrieved."
    )

    return {
        "city": city,
        "country": current.get("sys", {}).get("country", ""),
        "forecast": forecast,
        "summary": summary,
        "is_mock": False,
    }


@tool
async def get_weather_tool(city: str, forecast_days: int = 5) -> str:
    """Get weather forecast for a city.

    Args:
        city: City name (e.g. "Tokyo", "Paris", "New York")
        forecast_days: Number of days to forecast (1-7)

    Returns:
        JSON string with weather forecast and summary
    """
    if not s.apis.openweathermap_api_key:
        raise ValueError("OPENWEATHERMAP_API_KEY is not configured.")
        
    result = await _fetch_owm_weather(city, forecast_days)
    return str(result)
