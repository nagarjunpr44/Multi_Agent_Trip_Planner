from agents.booking.agent import _build_booking_package


def test_booking_package_uses_serpapi_price_and_provider_ids() -> None:
    package = _build_booking_package(
        constraints={
            "destinations": ["Paris"],
            "departure_date": "2026-06-01",
            "return_date": "2026-06-04",
        },
        flight_results={
            "options": [
                {
                    "id": "flight-token",
                    "airline": "Example Air",
                    "price_usd": 500,
                }
            ]
        },
        hotel_results={
            "options": [
                {
                    "id": "hotel-token",
                    "name": "Example Hotel",
                    "price_per_night_usd": 120,
                }
            ]
        },
        budget_analysis={
            "mid": {
                "activities_usd": 100,
                "food_usd": 150,
                "transport_usd": 40,
                "misc_usd": 25,
            }
        },
        session_id="abc123456789",
    )

    assert package["flight_offer_id"] == "flight-token"
    assert package["hotel_offer_id"] == "hotel-token"
    assert package["price_breakdown"]["flights_usd"] == 500
    assert package["price_breakdown"]["hotel_usd"] == 360
    assert package["total_estimated_usd"] == 1175
