from __future__ import annotations

import json

from langchain_core.tools import tool

# Fallback/Offline rates
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

@tool
async def convert_currency_tool(
    amount: float,
    from_currency: str,
    to_currency: str,
) -> str:
    """Convert an amount between currencies using approximate local rates.

    Args:
        amount: Amount to convert
        from_currency: Source currency code (e.g. USD, EUR, GBP, JPY)
        to_currency: Target currency code

    Returns:
        JSON with converted amount and exchange rate
    """
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    # Convert via USD as base using built-in rates
    from_rate = MOCK_RATES.get(from_currency, 1.0)
    to_rate = MOCK_RATES.get(to_currency, 1.0)

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
        "1_usd_equals": {to_currency: to_rate},
        "is_mock": True,
    })
