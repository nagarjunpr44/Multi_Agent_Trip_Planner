import pytest

from trip_planner.trip.geo import haversine_km, max_spread_km

LISBON = (38.7223, -9.1393)
PORTO = (41.1579, -8.6291)


def test_haversine_known_distance():
    assert haversine_km(LISBON, PORTO) == pytest.approx(274, abs=3)
    assert haversine_km(LISBON, LISBON) == 0


def test_max_spread():
    assert max_spread_km([]) == 0
    assert max_spread_km([LISBON]) == 0
    belem = (38.6916, -9.2160)
    assert max_spread_km([LISBON, belem, PORTO]) == pytest.approx(haversine_km(belem, PORTO))
