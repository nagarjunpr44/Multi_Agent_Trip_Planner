from __future__ import annotations

import httpx
from langchain_core.tools import tool
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import get_settings

OWM_BASE = "https://api.openweathermap.org/data/2.5"


def _mock_weather(city: str, days: int) -> dict:
    import random
    conditions = ["Sunny", "Partly Cloudy", "Clear", "Overcast", "Light Rain"]
    forecast = []
    from datetime import date, timedelta
    for i in range(min(days, 7)):
        day = date.today() + timedelta(days=i)
        forecast.append({
            "date": day.isoformat(),
            "condition": conditions[i % len(conditions)],
            "temp_high_c": round(18 + i * 1.5, 1),
            "temp_low_c": round(12 + i * 0.8, 1),
            "humidity_pct": 60 + i * 3,
            "precip_mm": round(i * 1.2, 1),
        })
    return {
        "city": city,
        "country": "N/A",
        "forecast": forecast,
        "summary": f"{city}: Mix of sun and clouds expected. Pleasant temperatures.",
        "is_mock": True,
    }


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
    s = get_settings()
    if s.app.mock_fallback or not s.apis.openweathermap_api_key:
        return str(_mock_weather(city, forecast_days))
    try:
        result = await _fetch_owm_weather(city, forecast_days)
        return str(result)
    except Exception as exc:
        result = _mock_weather(city, forecast_days)
        result["source"] = f"mock_fallback:{type(exc).__name__}"
        return str(result)
