from __future__ import annotations

import json

import httpx
from langchain_core.tools import tool
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import get_settings

FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"
EXCHANGERATE_API_URL = "https://v6.exchangerate-api.com/v6"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _convert_via_frankfurter(amount: float, from_currency: str, to_currency: str) -> dict:
    """Live ECB-backed rates via Frankfurter (no API key required)."""
    params = {
        "amount": amount,
        "from": from_currency.upper(),
        "to": to_currency.upper(),
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(FRANKFURTER_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    converted = float(data["rates"][to_currency.upper()])
    rate = round(converted / amount, 6) if amount else 0.0
    return {
        "from_currency": from_currency.upper(),
        "to_currency": to_currency.upper(),
        "original_amount": amount,
        "converted_amount": round(converted, 4),
        "exchange_rate": rate,
        "rate_date": data.get("date"),
        "source": "frankfurter",
    }


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _convert_via_exchangerate_api(
    amount: float, from_currency: str, to_currency: str, api_key: str
) -> dict:
    """ExchangeRate-API v6 pair conversion (requires EXCHANGE_RATES_API_KEY)."""
    base = from_currency.upper()
    to_code = to_currency.upper()
    url = f"{EXCHANGERATE_API_URL}/{api_key}/pair/{base}/{to_code}/{amount}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    if data.get("result") != "success":
        raise ValueError(data.get("error-type", "exchange rate API error"))

    conversion = data.get("conversion_result", amount)
    rate = float(data.get("conversion_rate", 0))
    return {
        "from_currency": base,
        "to_currency": to_code,
        "original_amount": amount,
        "converted_amount": round(float(conversion), 4),
        "exchange_rate": rate,
        "rate_date": data.get("time_last_update_utc"),
        "source": "exchangerate-api",
    }


@tool
async def convert_currency_tool(
    amount: float,
    from_currency: str,
    to_currency: str,
) -> str:
    """Convert an amount between currencies using live exchange rates.

    Args:
        amount: Amount to convert
        from_currency: Source currency code (e.g. USD, EUR, GBP, JPY)
        to_currency: Target currency code

    Returns:
        JSON with converted amount and exchange rate
    """
    from_currency = from_currency.upper().strip()
    to_currency = to_currency.upper().strip()

    if from_currency == to_currency:
        return json.dumps({
            "from_currency": from_currency,
            "to_currency": to_currency,
            "original_amount": amount,
            "converted_amount": amount,
            "exchange_rate": 1.0,
            "source": "identity",
        })

    settings = get_settings()
    api_key = settings.apis.exchange_rates_api_key

    try:
        if api_key and not api_key.startswith("..."):
            result = await _convert_via_exchangerate_api(
                amount, from_currency, to_currency, api_key
            )
        else:
            result = await _convert_via_frankfurter(amount, from_currency, to_currency)
    except Exception as exc:
        return json.dumps({
            "error": f"Currency conversion failed: {exc}",
            "from_currency": from_currency,
            "to_currency": to_currency,
        })

    return json.dumps(result)
