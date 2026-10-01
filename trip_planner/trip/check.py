"""Deterministic trip checks. No LLM, no network."""

from __future__ import annotations

from collections import Counter
from datetime import date, time, timedelta

from trip_planner.trip.geo import max_spread_km
from trip_planner.trip.models import Day, Issue, Stop, Trip

ARRIVAL_BUFFER_MIN = 120  # landing, bags, getting into town
NEAR_BUDGET_RATIO = 0.9
LONG_TRANSIT_MIN = 60
SCATTERED_KM = 10.0
EARLIEST_START_MIN = 7 * 60
LATEST_END_MIN = 23 * 60 + 30
PACE_LIMITS = {  # max stops, max active minutes (first start -> last end)
    "relaxed": (4, 8 * 60),
    "moderate": (6, 10 * 60),
    "packed": (8, 13 * 60),
}
DAY_MIN = 24 * 60
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def check_trip(trip: Trip) -> list[Issue]:
    """Every concrete problem with the trip, errors first."""
    issues = _check_budget(trip)
    if trip.start_date is None or trip.end_date is None:
        issues.append(
            Issue(
                code="missing_dates",
                severity="error",
                message="Trip has no start_date or end_date — set both before planning days.",
            )
        )
    elif trip.end_date < trip.start_date:
        issues.append(
            Issue(
                code="bad_dates",
                severity="error",
                message=f"end_date {trip.end_date} is before start_date {trip.start_date} "
                "— fix the dates.",
            )
        )
    else:
        issues += _check_days_cover_dates(trip)
        issues += _check_bookings(trip)
        seen_places: dict[str, date] = {}
        for day in sorted(trip.days, key=lambda d: d.date):
            issues += _check_day(trip, day, seen_places)
    # Errors first, then by date; trip-level issues (no date) lead each group.
    return sorted(issues, key=lambda i: (i.severity != "error", i.date or date.min))


def cost_breakdown(trip: Trip) -> dict:
    """{"flight", "hotel", "activities", "total", "budget" (or None), "remaining" (or None)}"""
    flight = trip.flight.price_usd if trip.flight else 0.0
    hotel = trip.hotel.total_usd if trip.hotel else 0.0
    activities = sum(s.est_cost_usd or 0.0 for d in trip.days for s in d.stops)
    total = flight + hotel + activities
    budget = trip.budget_usd
    return {
        "flight": round(flight, 2),
        "hotel": round(hotel, 2),
        "activities": round(activities, 2),
        "total": round(total, 2),
        "budget": None if budget is None else round(budget, 2),
        "remaining": None if budget is None else round(budget - total, 2),
    }


def _check_budget(trip: Trip) -> list[Issue]:
    budget = trip.budget_usd
    if budget is None:
        return []
    c = cost_breakdown(trip)
    total = c["total"]
    parts = (
        f"flight ${c['flight']:,.2f}, hotel ${c['hotel']:,.2f}, activities ${c['activities']:,.2f}"
    )
    if total > budget:
        return [
            Issue(
                code="over_budget",
                severity="error",
                message=f"Total ${total:,.2f} is ${total - budget:,.2f} over the "
                f"${budget:,.2f} budget ({parts}) — pick cheaper options.",
            )
        ]
    if total > NEAR_BUDGET_RATIO * budget:
        return [
            Issue(
                code="near_budget",
                severity="warning",
                message=f"Total ${total:,.2f} is over {NEAR_BUDGET_RATIO:.0%} of the "
                f"${budget:,.2f} budget ({parts}) — only ${budget - total:,.2f} left.",
            )
        ]
    return []


def _check_days_cover_dates(trip: Trip) -> list[Issue]:
    assert trip.start_date and trip.end_date
    n_days = (trip.end_date - trip.start_date).days + 1
    wanted = {trip.start_date + timedelta(days=i) for i in range(n_days)}
    have = Counter(day.date for day in trip.days)
    issues = []
    for d in sorted(wanted | have.keys()):
        if d not in have:
            msg = f"{_label(trip, d)}: no Day planned for this date — add one."
        elif d not in wanted:
            msg = (
                f"Day for {d:%a %Y-%m-%d} is outside the trip ({trip.start_date} to "
                f"{trip.end_date}) — remove it or change the trip dates."
            )
        elif have[d] > 1:
            msg = f"{_label(trip, d)}: {have[d]} Days share this date — merge them into one."
        else:
            continue
        issues.append(Issue(code="days_mismatch", severity="error", message=msg, date=d))
    return issues


def _check_bookings(trip: Trip) -> list[Issue]:
    issues = []
    hotel = trip.hotel
    if hotel and (hotel.check_in != trip.start_date or hotel.check_out != trip.end_date):
        issues.append(
            Issue(
                code="hotel_dates",
                severity="warning",
                message=f"Hotel {hotel.name} is booked {hotel.check_in} to {hotel.check_out} "
                f"but the trip runs {trip.start_date} to {trip.end_date} — re-search the hotel "
                "for the trip dates.",
            )
        )
    flight = trip.flight
    if flight and flight.depart_at.date() != trip.start_date:
        issues.append(
            Issue(
                code="flight_dates",
                severity="warning",
                message=f"Flight {flight.airline} departs {flight.depart_at:%Y-%m-%d} but the "
                f"trip starts {trip.start_date} — re-search flights for the start date.",
            )
        )
    return issues


def _check_day(trip: Trip, day: Day, seen_places: dict[str, date]) -> list[Issue]:
    label = _label(trip, day.date)

    def issue(code: str, severity: str, msg: str, stop: Stop | None = None) -> Issue:
        return Issue(
            code=code,
            severity=severity,
            message=f"{label}: {msg}",
            date=day.date,
            stop_id=stop.id if stop else None,
        )

    if not day.stops:
        return [issue("empty_day", "warning", "no stops planned — add some or merge days.")]

    issues = []
    stops = sorted(day.stops, key=lambda s: s.start)
    arrival = _arrival_ready_min(trip, day.date)
    for i, stop in enumerate(stops):
        name, start, end = stop.place.name, _min(stop.start), _end_min(stop)
        travel = stop.travel_from_prev_min or 0

        closed = _closed_reason(stop, day.date)
        if closed:
            issues.append(
                issue("closed", "error", f"{name} {closed} — move it or pick another day.", stop)
            )

        if i > 0:
            prev = stops[i - 1]
            ready = _end_min(prev) + travel
            if start < ready:
                via = f" and it takes {travel} min to get there" if travel else ""
                msg = (
                    f"{name} starts at {_fmt(start)} but {prev.place.name} ends at "
                    f"{_fmt(_end_min(prev))}{via} — start it at {_fmt(ready)} or later."
                )
                issues.append(issue("overlap", "error", msg, stop))

        if arrival is not None and start < arrival:
            msg = (
                f"{name} starts at {_fmt(start)} but the flight lands at "
                f"{_fmt(arrival - ARRIVAL_BUFFER_MIN)} — start it at {_fmt(arrival)} or later."
            )
            issues.append(issue("arrival", "error", msg, stop))

        if travel > LONG_TRANSIT_MIN:
            msg = (
                f"getting to {name} takes {travel} min — pick something closer or "
                "regroup the day by area."
            )
            issues.append(issue("long_transit", "warning", msg, stop))

        if start < EARLIEST_START_MIN or end > LATEST_END_MIN:
            msg = (
                f"{name} runs {_fmt(start)}–{_fmt(end)}, outside "
                f"{_fmt(EARLIEST_START_MIN)}–{_fmt(LATEST_END_MIN)} — shift it."
            )
            issues.append(issue("late", "warning", msg, stop))

        first = seen_places.get(stop.place.place_id)
        if first is None:
            seen_places[stop.place.place_id] = day.date
        else:
            msg = (
                f"{name} is already planned on {_label(trip, first)} — replace this "
                "visit with something new."
            )
            issues.append(issue("duplicate_place", "warning", msg, stop))

    max_stops, max_active = PACE_LIMITS[trip.pace]
    active = max(_end_min(s) for s in stops) - _min(stops[0].start)
    if len(stops) > max_stops or active > max_active:
        msg = (
            f"{len(stops)} stops over {active / 60:.1f}h is too much for a {trip.pace} pace "
            f"(max {max_stops} stops, {max_active // 60}h) — drop or move a stop."
        )
        issues.append(issue("too_packed", "warning", msg))

    points = [
        (s.place.lat, s.place.lng)
        for s in stops
        if s.place.lat is not None and s.place.lng is not None
    ]
    spread = max_spread_km(points)
    if spread > SCATTERED_KM:
        msg = f"stops are up to {spread:.1f} km apart — keep the day within one area."
        issues.append(issue("scattered", "warning", msg))
    return issues


def _closed_reason(stop: Stop, d: date) -> str | None:
    """Why the stop's visit window isn't inside opening hours, or None if it is (or unknown)."""
    hours = stop.place.hours
    if hours is None:
        return None
    weekday = d.weekday()
    start, end = _min(stop.start), _end_min(stop)
    # Opening intervals in minutes relative to this day's midnight, including the
    # previous night's after-midnight hours and the next day's for late visits.
    intervals = []
    for offset in (-1, 0, 1):
        for p in hours:
            if p.weekday == (weekday + offset) % 7:
                o, c = _min(p.open), _min(p.close)
                if c <= o:
                    c += DAY_MIN
                intervals.append((o + offset * DAY_MIN, c + offset * DAY_MIN))
    # Merge back-to-back intervals so e.g. 24h places cover visits past midnight.
    merged: list[list[int]] = []
    for o, c in sorted(intervals):
        if merged and o <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], c)
        else:
            merged.append([o, c])
    if any(o <= start and end <= c for o, c in merged):
        return None
    day_name = WEEKDAYS[weekday]
    today = sorted(f"{p.open:%H:%M}–{p.close:%H:%M}" for p in hours if p.weekday == weekday)
    if not today:
        return f"is closed on {day_name}s"
    return f"is open {', '.join(today)} on {day_name}s but is planned {_fmt(start)}–{_fmt(end)}"


def _arrival_ready_min(trip: Trip, d: date) -> int | None:
    """Earliest stop start on the arrival date, or None if d isn't the arrival date."""
    if trip.flight is None or trip.flight.arrive_at.date() != d:
        return None
    return _min(trip.flight.arrive_at.time()) + ARRIVAL_BUFFER_MIN


def _label(trip: Trip, d: date) -> str:
    assert trip.start_date
    return f"Day {(d - trip.start_date).days + 1} ({d:%a %Y-%m-%d})"


def _min(t: time) -> int:
    return t.hour * 60 + t.minute


def _end_min(stop: Stop) -> int:
    return _min(stop.start) + stop.duration_min


def _fmt(minutes: int) -> str:
    """Minutes since midnight as HH:MM; past midnight shows +1d."""
    days, m = divmod(minutes, DAY_MIN)
    suffix = f" (+{days}d)" if days else ""
    return f"{m // 60:02d}:{m % 60:02d}{suffix}"
