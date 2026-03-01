from __future__ import annotations

import json

import httpx
from langchain_core.tools import tool
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import get_settings

MOCK_RATES = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.79,
    "JPY": 149.50,
    "AUD": 1.53,
    "CAD": 1.36,
    "CHF": 0.88,
    "CNY": 7.24,
    "INR": 83.12,
    "BRL": 4.97,
    "MXN": 17.15,
    "SGD": 1.34,
    "THB": 35.80,
    "MYR": 4.72,
    "IDR": 15750.0,
    "VND": 24500.0,
    "HKD": 7.82,
    "KRW": 1325.0,
    "TRY": 32.14,
}


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _fetch_live_rates(base_currency: str, api_key: str) -> dict[str, float]:
    url = f"https://openexchangerates.org/api/latest.json"
    async with httpx.AsyncClient(timeout=8.0) as client:
        resp = await client.get(url, params={"app_id": api_key, "base": "USD"})
        resp.raise_for_status()
        data = resp.json()
    return data.get("rates", {})


@tool
async def convert_currency_tool(
    amount: float,
    from_currency: str,
    to_currency: str,
) -> str:
    """Convert an amount between currencies.

    Args:
        amount: Amount to convert
        from_currency: Source currency code (e.g. USD, EUR, GBP, JPY)
        to_currency: Target currency code

    Returns:
        JSON with converted amount and exchange rate
    """
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()
    s = get_settings()

    rates = MOCK_RATES.copy()
    is_mock = True

    if not s.app.mock_fallback and s.apis.exchange_rates_api_key:
        try:
            rates = await _fetch_live_rates("USD", s.apis.exchange_rates_api_key)
            is_mock = False
        except Exception:
            pass  # fall back to mock rates

    # Convert via USD as base
    from_rate = rates.get(from_currency, 1.0)
    to_rate = rates.get(to_currency, 1.0)

    # amount in from_currency → USD → to_currency
    amount_usd = amount / from_rate
    converted = round(amount_usd * to_rate, 4)
    rate = round(to_rate / from_rate, 6)

    return json.dumps({
        "from_currency": from_currency,
        "to_currency": to_currency,
        "original_amount": amount,
        "converted_amount": converted,
        "exchange_rate": rate,
        "1_usd_equals": {to_currency: rates.get(to_currency, 1.0)},
        "is_mock": is_mock,
    })
