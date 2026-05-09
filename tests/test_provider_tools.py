from tools.flights import normalize_airport_code
from tools.hotels import normalize_hotel_city


def test_normalize_airport_code_maps_common_cities() -> None:
    assert normalize_airport_code("San Francisco") == "SFO"
    assert normalize_airport_code("Tokyo") == "HND"
    assert normalize_airport_code("Paris") == "CDG"


def test_normalize_airport_code_preserves_iata_codes() -> None:
    assert normalize_airport_code("lax") == "LAX"
    assert normalize_airport_code(" JFK ") == "JFK"


def test_normalize_hotel_city_keeps_serpapi_query_readable() -> None:
    assert normalize_hotel_city("nyc") == "New York"
    assert normalize_hotel_city("san francisco") == "San Francisco"
