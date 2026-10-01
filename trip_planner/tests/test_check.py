from datetime import date, datetime, time, timedelta

from trip_planner.trip.check import check_trip, cost_breakdown
from trip_planner.trip.models import (
    Day,
    FlightOption,
    HotelOption,
    OpenPeriod,
    Place,
    Stop,
    Trip,
)

MON = date(2026, 5, 4)  # a Monday
TUE = MON + timedelta(days=1)


def stop(name, start="10:00", minutes=60, hours=None, lat=None, lng=None, **kw) -> Stop:
    place = Place(place_id=kw.pop("place_id", name), name=name, hours=hours, lat=lat, lng=lng)
    return Stop(place=place, start=time.fromisoformat(start), duration_min=minutes, **kw)


def trip(*days_stops, start=MON, **kw) -> Trip:
    """One Day per positional list of stops, starting at `start`."""
    days = [Day(date=start + timedelta(days=i), stops=s) for i, s in enumerate(days_stops)]
    end = start + timedelta(days=max(len(days) - 1, 0))
    return Trip(**{"start_date": start, "end_date": end, "days": days, **kw})


def daily(open_="09:00", close="18:00", weekdays=range(7)) -> list[OpenPeriod]:
    o, c = time.fromisoformat(open_), time.fromisoformat(close)
    return [OpenPeriod(weekday=w, open=o, close=c) for w in weekdays]


def codes(t: Trip) -> list[str]:
    return [i.code for i in check_trip(t)]


def flight(depart: datetime, arrive: datetime, price=500.0) -> FlightOption:
    return FlightOption(
        id="f1",
        airline="TAP",
        origin="JFK",
        destination="LIS",
        depart_at=depart,
        arrive_at=arrive,
        price_usd=price,
    )


def hotel(check_in=MON, check_out=TUE, total=200.0) -> HotelOption:
    return HotelOption(
        id="h1",
        name="Hotel A",
        check_in=check_in,
        check_out=check_out,
        price_per_night_usd=total,
        total_usd=total,
    )


def test_clean_trip_has_no_issues():
    assert check_trip(trip([stop("A")], [stop("B")])) == []


# --- dates -----------------------------------------------------------------


def test_missing_dates_skips_day_checks():
    t = Trip(days=[Day(date=MON)])
    assert codes(t) == ["missing_dates"]


def test_bad_dates():
    t = Trip(start_date=TUE, end_date=MON)
    assert codes(t) == ["bad_dates"]


def test_days_mismatch_missing_extra_and_duplicate():
    t = Trip(
        start_date=MON,
        end_date=MON + timedelta(days=2),
        days=[
            Day(date=MON, stops=[stop("A")]),
            Day(date=MON, stops=[stop("B")]),
            Day(date=MON + timedelta(days=5), stops=[stop("C")]),
        ],
    )
    issues = [i for i in check_trip(t) if i.code == "days_mismatch"]
    assert [i.date for i in issues] == [MON, TUE, MON + timedelta(days=2), MON + timedelta(days=5)]
    assert "2 Days share this date" in issues[0].message
    assert issues[1].message.startswith("Day 2 (Tue 2026-05-05): no Day planned")
    assert "outside the trip" in issues[3].message


# --- opening hours ---------------------------------------------------------


def test_closed_on_weekday():
    s = stop("Museu Gulbenkian", hours=daily(weekdays=[0, 2, 3, 4, 5, 6]))
    [issue] = check_trip(trip([], [s]))[:1]
    assert issue.code == "closed" and issue.stop_id == s.id and issue.date == TUE
    assert issue.message == (
        "Day 2 (Tue 2026-05-05): Museu Gulbenkian is closed on Tuesdays "
        "— move it or pick another day."
    )


def test_closed_when_visit_runs_past_closing():
    s = stop("Shop", start="17:30", minutes=60, hours=daily())
    [issue] = check_trip(trip([s]))
    assert issue.code == "closed" and "open 09:00–18:00 on Mondays" in issue.message


def test_never_open_vs_unknown_hours():
    assert codes(trip([stop("A", hours=[])])) == ["closed"]
    assert codes(trip([stop("A", hours=None)])) == []


def test_overnight_hours():
    bar = daily("20:00", "02:00")
    assert codes(trip([stop("Bar", "22:00", 180, hours=bar)])) == ["late"]  # 22:00–01:00
    # 01:00 Tuesday is covered by Monday night's period.
    only_monday = daily("20:00", "02:00", weekdays=[0])
    assert codes(
        trip(
            [stop("Bar", "08:00", 60, hours=only_monday)],
            [stop("Bar2", "07:00", 60, hours=only_monday)],
        )
    ) == ["closed", "closed"]
    assert "closed" not in codes(trip([], [stop("Bar", "01:00", 60, hours=only_monday)]))


def test_24h_place():
    always = daily("00:00", "00:00")
    assert codes(trip([stop("Park", "07:00", 60, hours=always)])) == []
    # Spills past midnight into the next 24h day: open, just late.
    assert codes(trip([stop("Park", "23:00", 120, hours=always)])) == ["late"]


# --- schedule --------------------------------------------------------------


def test_overlap_uses_sorted_stops_and_travel():
    a = stop("A", "10:00", 60)
    b = stop("B", "11:10", 60, travel_from_prev_min=15)
    issues = check_trip(trip([b, a]))  # unsorted on purpose
    assert [i.code for i in issues] == ["overlap"]
    assert issues[0].stop_id == b.id
    assert "start it at 11:15 or later" in issues[0].message
    ok = stop("B", "11:15", 60, travel_from_prev_min=15)
    assert codes(trip([ok, a])) == []


def test_arrival_buffer():
    f = flight(datetime(2026, 5, 3, 20, 0), datetime(2026, 5, 4, 9, 0))
    early, ok = stop("A", "10:30"), stop("B", "12:00")
    issues = check_trip(trip([early, ok], flight=f))
    assert [(i.code, i.stop_id) for i in issues] == [("arrival", early.id), ("flight_dates", None)]
    assert "lands at 09:00 — start it at 11:00 or later" in issues[0].message


def test_flight_dates_allows_next_day_arrival():
    f = flight(datetime(2026, 5, 4, 1, 0), datetime(2026, 5, 4, 5, 0))
    assert codes(trip([stop("A")], flight=f)) == []
    f = flight(datetime(2026, 5, 5, 1, 0), datetime(2026, 5, 5, 5, 0))
    assert codes(trip([stop("A")], [stop("B")], flight=f)) == ["flight_dates"]


def test_hotel_dates():
    assert codes(trip([stop("A")], [stop("B")], hotel=hotel())) == []
    bad = hotel(check_out=TUE + timedelta(days=1))
    assert codes(trip([stop("A")], [stop("B")], hotel=bad)) == ["hotel_dates"]


def test_too_packed_by_count_and_span():
    five = [stop(f"S{i}", f"{9 + i * 2:02d}:00", 60) for i in range(5)]  # 09:00–18:00
    assert codes(trip(five, pace="relaxed")) == ["too_packed"]
    assert codes(trip(five, pace="moderate")) == []
    long_day = [stop("A", "08:00", 60), stop("B", "18:00", 60)]  # 11h span
    assert codes(trip(long_day, pace="moderate")) == ["too_packed"]
    assert codes(trip(long_day, pace="packed")) == []


def test_long_transit():
    issues = check_trip(trip([stop("A", "09:00"), stop("B", "12:00", travel_from_prev_min=61)]))
    assert [i.code for i in issues] == ["long_transit"]
    assert codes(trip([stop("A", "09:00"), stop("B", "12:00", travel_from_prev_min=60)])) == []


def test_scattered_ignores_missing_coords():
    lisbon = stop("Baixa", "09:00", lat=38.7110, lng=-9.1366)
    sintra = stop("Sintra", "12:00", lat=38.7973, lng=-9.3904)
    nowhere = stop("Somewhere", "15:00")
    assert codes(trip([lisbon, sintra, nowhere])) == ["scattered"]
    belem = stop("Belem", "12:00", lat=38.6916, lng=-9.2160)
    assert codes(trip([lisbon, belem, nowhere])) == []


def test_late_and_early():
    assert codes(trip([stop("A", "06:30")])) == ["late"]
    assert codes(trip([stop("A", "22:30", 61)])) == ["late"]
    assert codes(trip([stop("A", "07:00")], [stop("B", "22:30", 60)])) == []


def test_empty_day():
    issues = check_trip(trip([stop("A")], []))
    assert [(i.code, i.date) for i in issues] == [("empty_day", TUE)]


def test_duplicate_place_flags_later_visits_only():
    first, same_day, next_day = stop("A", "09:00"), stop("A", "12:00"), stop("A", "10:00")
    issues = check_trip(trip([same_day, first], [next_day]))
    assert [(i.code, i.stop_id) for i in issues] == [
        ("duplicate_place", same_day.id),
        ("duplicate_place", next_day.id),
    ]
    assert "already planned on Day 1 (Mon 2026-05-04)" in issues[1].message


def test_errors_first_then_by_date():
    t = trip([stop("A", "06:00")], [stop("B", hours=[])])
    assert [(i.severity, i.date) for i in check_trip(t)] == [("error", TUE), ("warning", MON)]


# --- budget ----------------------------------------------------------------


def test_cost_breakdown():
    t = trip(
        [stop("A", est_cost_usd=10.123), stop("B", "12:00")],
        flight=flight(datetime(2026, 5, 4, 1), datetime(2026, 5, 4, 5), price=300.1),
        hotel=hotel(check_out=MON, total=99.9),
        budget_usd=1000,
    )
    assert cost_breakdown(t) == {
        "flight": 300.1,
        "hotel": 99.9,
        "activities": 10.12,
        "total": 410.12,
        "budget": 1000,
        "remaining": 589.88,
    }
    assert cost_breakdown(Trip()) == {
        "flight": 0,
        "hotel": 0,
        "activities": 0,
        "total": 0,
        "budget": None,
        "remaining": None,
    }


def test_budget_boundaries():
    def at(cost):
        return codes(trip([stop("A", est_cost_usd=cost)], budget_usd=100))

    assert at(90) == []
    assert at(90.01) == ["near_budget"]
    assert at(100) == ["near_budget"]
    assert at(100.01) == ["over_budget"]
    assert codes(trip([stop("A", est_cost_usd=1e6)])) == []  # no budget set
