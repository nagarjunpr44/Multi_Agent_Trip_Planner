"""Tools the planner LLM sees: an args model (the schema + description the LLM reads)
and a handler `async (state, **args) -> (result, state_updates)` per tool.

Handlers never mutate `state`; they return the keys that changed.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Awaitable, Callable
from typing import Any, Literal, NamedTuple

from pydantic import BaseModel, Field, ValidationError

from trip_planner import store
from trip_planner.agent import research
from trip_planner.tools import ToolError, flights, hotels, places, routes, weather, web
from trip_planner.trip.check import check_trip, cost_breakdown
from trip_planner.trip.models import Day, FlightOption, HotelOption, Place, Stop, Trip

MAX_DAYS = 60
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ── Helpers ────────────────────────────────────────────────────────────────

def _load(state: dict) -> Trip:
    return Trip.model_validate(state["trip"])


def _save(trip: Trip) -> dict:
    trip.status = "planning"  # any edit needs a fresh approval
    trip.version += 1
    return {"trip": trip.model_dump(mode="json")}


def _day(trip: Trip, d: dt.date) -> Day:
    day = trip.day_for(d)
    if day is None:
        if not trip.days:
            raise ToolError("The trip has no dates yet; set start_date/end_date first")
        raise ToolError(f"No day {d}; trip days are {trip.days[0].date} to {trip.days[-1].date}")
    return day


def _sort(day: Day) -> None:
    day.stops.sort(key=lambda s: s.start)


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(
        (lng2 - lng1) / 2
    ) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _coords(p: Place) -> tuple[float, float] | None:
    return (p.lat, p.lng) if p.lat is not None and p.lng is not None else None


def hours_summary(hours: list | None) -> str:
    """"Mon–Fri 09:00–17:00; Sat 10:00–14:00; Sun closed" or "hours unknown"."""
    if hours is None:
        return "hours unknown"
    per_day = [
        ", ".join(
            f"{p.open:%H:%M}–{p.close:%H:%M}"
            for p in sorted(hours, key=lambda p: p.open)
            if p.weekday == wd
        )
        or "closed"
        for wd in range(7)
    ]
    groups: list[list] = []  # [first weekday, last weekday, text]
    for wd, text in enumerate(per_day):
        if groups and groups[-1][2] == text:
            groups[-1][1] = wd
        else:
            groups.append([wd, wd, text])
    return "; ".join(
        f"{WEEKDAYS[a]}{'–' + WEEKDAYS[b] if b > a else ''} {text}" for a, b, text in groups
    )


def _place_brief(p: Place) -> dict:
    return {
        "place_id": p.place_id,
        "name": p.name,
        "rating": p.rating,
        "price_level": p.price_level,
        "address": p.address,
        "lat": round(p.lat, 4) if p.lat is not None else None,
        "lng": round(p.lng, 4) if p.lng is not None else None,
        "hours": hours_summary(p.hours),
    }


def _merge_places(state: dict, found: list[Place]) -> dict:
    return {"places": {**state.get("places", {}), **_by_id(found, "place_id")}}


def _by_id(items: list, key: str = "id") -> dict[str, dict]:
    return {getattr(i, key): i.model_dump(mode="json") for i in items}


def _select(state: dict, key: str, option_id: str) -> dict:
    options = state.get(key) or {}
    if option_id not in options:
        valid = ", ".join(options) or "none yet, search first"
        raise ToolError(f"Unknown option_id {option_id!r}. Valid ids: {valid}")
    return options[option_id]


# ── Tool args (the LLM-facing schema) ──────────────────────────────────────

class UpdateTripArgs(BaseModel):
    """Set or change trip fields; pass only what changes. Changing dates rebuilds the \
day list, keeping days (and their stops) that are still in range."""

    title: str | None = None
    origin: str | None = Field(None, description="Home city or airport")
    destinations: list[str] | None = Field(None, description="Cities, in visiting order")
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    travelers: int | None = Field(None, ge=1)
    budget_usd: float | None = Field(None, description="Total for the whole party")
    tier: Literal["budget", "mid", "luxury"] | None = None
    pace: Literal["relaxed", "moderate", "packed"] | None = None
    prefs: list[str] | None = Field(None, description="Replaces the list, e.g. ['art']")
    constraints: list[str] | None = Field(
        None, description="Replaces the list, e.g. ['vegetarian']"
    )


class SearchFlightsArgs(BaseModel):
    """Search flights. Defaults: trip origin → first destination, trip start/end dates, \
trip travelers. Prices are totals for the party."""

    origin: str | None = Field(None, description="City or IATA code")
    destination: str | None = Field(None, description="City or IATA code")
    depart: dt.date | None = None
    return_date: dt.date | None = None
    cabin: Literal["economy", "premium_economy", "business", "first"] = "economy"


class SelectOptionArgs(BaseModel):
    option_id: str = Field(description="An id from the latest search results")


class SearchHotelsArgs(BaseModel):
    """Search hotels in the first destination for the trip dates and travelers."""

    near: str | None = Field(None, description="Neighborhood to stay near, e.g. 'Alfama'")
    max_price_per_night: float | None = None
    min_stars: int | None = Field(None, ge=1, le=5)


class SearchPlacesArgs(BaseModel):
    """Find real places (sights, restaurants, museums…) with rating, hours and location. \
Only places found here or by research_city can be added as stops. Each call takes a while, \
so pass every query for an area in one call; prefer broad queries ('historic sights', \
'seafood restaurant') over one search per landmark."""

    queries: list[str] = Field(
        min_length=1, max_length=8,
        description="What to look for, e.g. ['pastel de nata', 'fado restaurant', 'viewpoint']",
    )
    near: str | None = Field(None, description="Area or city; defaults to the first destination")


class PlaceIdArgs(BaseModel):
    """Full details for one place (refreshes opening hours)."""

    place_id: str


class AddStopArgs(BaseModel):
    """Add a stop to a day. place_id must come from search_places or research_city."""

    date: dt.date
    place_id: str
    start: dt.time = Field(description="Local start time, HH:MM")
    duration_min: int = Field(gt=0)
    note: str = Field(description="One line: why go, tips")
    est_cost_usd: float | None = Field(None, description="Total for the party, if known")


class UpdateStopArgs(BaseModel):
    """Change a stop; a new date moves it to that day."""

    stop_id: str
    date: dt.date | None = None
    start: dt.time | None = Field(None, description="HH:MM")
    duration_min: int | None = Field(None, gt=0)
    note: str | None = None
    est_cost_usd: float | None = None


class RemoveStopArgs(BaseModel):
    """Remove a stop from the trip."""

    stop_id: str


class SetDayArgs(BaseModel):
    """Set a day's area (the neighborhood it is built around) and/or notes."""

    date: dt.date
    area: str | None = None
    notes: str | None = None


class CheckTripArgs(BaseModel):
    """Fill travel times between stops, then return every problem (closed venues, \
overlaps, budget…) and the cost breakdown. Run after edits; fix every error."""


class WebSearchArgs(BaseModel):
    """Search the web for current info (events, closures, tips)."""

    query: str


class WeatherArgs(BaseModel):
    """Daily forecast for the trip dates (empty beyond the forecast window)."""

    city: str | None = Field(None, description="Defaults to where the trip is based")


class ResearchArgs(BaseModel):
    """Have a researcher read the web and places for a city and return a short brief: \
areas, must-sees, named places matching the focus (with place_ids), tips."""

    city: str
    focus: str = Field(description="What matters for this trip, e.g. 'food markets, art'")


class PreferenceArgs(BaseModel):
    """Remember a durable fact about the user for future trips (diet, mobility, pace…)."""

    key: str = Field(description="Short key, e.g. 'diet'")
    value: str


class ApprovalArgs(BaseModel):
    """Ask the user to approve the finished plan before booking. Only when the user says \
they are happy with it or want to book."""

    summary: str = Field(description="2–4 lines: what is planned and the total cost")


# ── Handlers ───────────────────────────────────────────────────────────────

async def update_trip(state: dict, **changes: Any):
    trip = Trip.model_validate({**_load(state).model_dump(), **changes})
    if trip.start_date and trip.end_date:
        n = (trip.end_date - trip.start_date).days + 1
        if n < 1:
            raise ToolError("end_date is before start_date")
        if n > MAX_DAYS:
            raise ToolError(f"Trips are limited to {MAX_DAYS} days")
        old = {d.date: d for d in trip.days}
        dates = [trip.start_date + dt.timedelta(days=i) for i in range(n)]
        trip.days = [old.get(d) or Day(date=d) for d in dates]
    if not trip.title and trip.destinations and trip.start_date:
        trip.title = f"{', '.join(trip.destinations)} · {trip.start_date:%b} {trip.start_date.day}"
    return {"updated": sorted(changes), "days": len(trip.days)}, _save(trip)


async def search_flights(
    state: dict,
    origin: str | None = None,
    destination: str | None = None,
    depart: dt.date | None = None,
    return_date: dt.date | None = None,
    cabin: str = "economy",
):
    trip = _load(state)
    origin = origin or trip.origin
    destination = destination or (trip.destinations[0] if trip.destinations else None)
    depart = depart or trip.start_date
    if not (origin and destination and depart):
        raise ToolError("Need origin, destination and depart date (or set them on the trip)")
    options = await flights.search_flights(
        origin, destination, depart, return_date or trip.end_date, adults=trip.travelers,
        cabin=cabin,
    )
    stored = {**state.get("flight_options", {}), **_by_id(options)}
    keys = {"id", "airline", "price_usd", "depart_at", "arrive_at", "stops", "duration_min"}
    return [o.model_dump(mode="json", include=keys) for o in options], {"flight_options": stored}


async def select_flight(state: dict, option_id: str):
    trip = _load(state)
    trip.flight = FlightOption.model_validate(_select(state, "flight_options", option_id))
    return f"Selected {trip.flight.airline} ${trip.flight.price_usd:,.0f}", _save(trip)


async def search_hotels(
    state: dict,
    near: str | None = None,
    max_price_per_night: float | None = None,
    min_stars: int | None = None,
):
    trip = _load(state)
    if not (trip.destinations and trip.start_date and trip.end_date):
        raise ToolError("Set the destination and dates on the trip first")
    options = await hotels.search_hotels(
        trip.destinations[0], trip.start_date, trip.end_date, adults=trip.travelers,
        max_price_per_night=max_price_per_night, min_stars=min_stars, near=near,
    )
    stored = {**state.get("hotel_options", {}), **_by_id(options)}
    keys = {"id", "name", "address", "price_per_night_usd", "total_usd", "rating", "stars"}
    return [o.model_dump(mode="json", include=keys) for o in options], {"hotel_options": stored}


async def select_hotel(state: dict, option_id: str):
    trip = _load(state)
    trip.hotel = HotelOption.model_validate(_select(state, "hotel_options", option_id))
    return f"Selected {trip.hotel.name} ${trip.hotel.total_usd:,.0f} total", _save(trip)


async def search_places(state: dict, queries: list[str], near: str | None = None):
    trip = _load(state)
    near = near or (trip.destinations[0] if trip.destinations else None)
    if not near:
        raise ToolError("Say where to search (near) or set the destination first")
    found = await places.search_many(queries, near, max_results=5)
    return [_place_brief(p) for p in found], _merge_places(state, found)


async def get_place_details(state: dict, place_id: str):
    p = await places.get_place(place_id)
    return {**_place_brief(p), "types": p.types, "website": p.website}, _merge_places(state, [p])


async def add_stop(
    state: dict,
    date: dt.date,
    place_id: str,
    start: dt.time,
    duration_min: int,
    note: str,
    est_cost_usd: float | None = None,
):
    place = (state.get("places") or {}).get(place_id)
    if place is None:
        raise ToolError(f"Unknown place_id {place_id!r}; find it with search_places first")
    trip = _load(state)
    day = _day(trip, date)
    stop = Stop(
        place=Place.model_validate(place), start=start, duration_min=duration_min, note=note,
        est_cost_usd=est_cost_usd,
    )
    day.stops.append(stop)
    _sort(day)
    return {"stop_id": stop.id}, _save(trip)


async def update_stop(state: dict, stop_id: str, date: dt.date | None = None, **fields: Any):
    trip = _load(state)
    found = trip.find_stop(stop_id)
    if found is None:
        raise ToolError(f"Unknown stop_id {stop_id!r}")
    day, stop = found
    if date and date != day.date:
        new_day = _day(trip, date)
        day.stops = [s for s in day.stops if s.id != stop_id]
        new_day.stops.append(stop)
        day = new_day
    for key, value in fields.items():
        setattr(stop, key, value)
    _sort(day)
    return f"Updated stop {stop_id}", _save(trip)


async def remove_stop(state: dict, stop_id: str):
    trip = _load(state)
    found = trip.find_stop(stop_id)
    if found is None:
        raise ToolError(f"Unknown stop_id {stop_id!r}")
    day, _ = found
    day.stops = [s for s in day.stops if s.id != stop_id]
    return f"Removed stop {stop_id}", _save(trip)


async def set_day(state: dict, date: dt.date, **fields: Any):
    trip = _load(state)
    day = _day(trip, date)
    for key, value in fields.items():
        setattr(day, key, value)
    return f"Updated {date}", _save(trip)


async def check(state: dict):
    trip = _load(state)
    before = trip.model_dump()
    for day in trip.days:
        prev = None
        for stop in day.stops:
            stop.travel_from_prev_min = stop.travel_mode = None
            a = _coords(prev.place) if prev else None
            b = _coords(stop.place)
            if a and b:
                mode = "walk" if _km(a, b) < 1.5 else "transit"
                stop.travel_from_prev_min = await routes.travel_minutes(a, b, mode)
                stop.travel_mode = mode
            prev = stop
    result = {
        "issues": [i.model_dump(mode="json") for i in check_trip(trip)],
        "cost": cost_breakdown(trip),
    }
    return result, (_save(trip) if trip.model_dump() != before else {})


async def web_search(state: dict, query: str):
    return await web.web_search(query), {}


async def get_weather(state: dict, city: str | None = None):
    trip = _load(state)
    if not (trip.start_date and trip.end_date):
        raise ToolError("Set the trip dates first")
    coords = None
    if not city:
        if trip.hotel and trip.hotel.lat is not None and trip.hotel.lng is not None:
            coords = (trip.hotel.lat, trip.hotel.lng)
        else:
            stops = (s.place for d in trip.days for s in d.stops)
            coords = next((c for p in stops if (c := _coords(p))), None)
    if coords is None:
        name = city or (trip.destinations[0] if trip.destinations else "")
        if not name:
            raise ToolError("Say which city")
        coords = await weather.geocode(name)
    forecast = await weather.get_weather(*coords, trip.start_date, trip.end_date)
    return forecast or "No forecast yet: the trip dates are beyond the forecast window", {}


async def research_city(state: dict, city: str, focus: str):
    brief, found = await research.research_city(city, focus)
    # Hours and location come along so the planner can add these without re-fetching.
    listed = [_place_brief(Place.model_validate(p)) for p in found.values()]
    result = {"brief": brief, "places": listed}
    return result, ({"places": {**state.get("places", {}), **found}} if found else {})


async def remember_preference(state: dict, key: str, value: str):
    await store.set_preference(key, value, user_id=state.get("user_id") or "local")
    return f"Saved {key}={value}", {}


# ── Registry ───────────────────────────────────────────────────────────────

Handler = Callable[..., Awaitable[tuple[Any, dict]]]


class Tool(NamedTuple):
    args: type[BaseModel]
    handler: Handler | None  # None: handled by the graph (request_approval)
    label: str  # shown in the UI while the tool runs
    description: str | None = None  # defaults to the args docstring


TOOLS: dict[str, Tool] = {
    "update_trip": Tool(UpdateTripArgs, update_trip, "Updating trip"),
    "search_flights": Tool(SearchFlightsArgs, search_flights, "Searching flights"),
    "select_flight": Tool(SelectOptionArgs, select_flight, "Choosing flight",
                          "Choose a flight from search_flights results."),
    "search_hotels": Tool(SearchHotelsArgs, search_hotels, "Searching hotels"),
    "select_hotel": Tool(SelectOptionArgs, select_hotel, "Choosing hotel",
                         "Choose a hotel from search_hotels results."),
    "search_places": Tool(SearchPlacesArgs, search_places, "Searching places"),
    "get_place_details": Tool(PlaceIdArgs, get_place_details, "Checking place"),
    "add_stop": Tool(AddStopArgs, add_stop, "Adding stop"),
    "update_stop": Tool(UpdateStopArgs, update_stop, "Updating stop"),
    "remove_stop": Tool(RemoveStopArgs, remove_stop, "Removing stop"),
    "set_day": Tool(SetDayArgs, set_day, "Updating day"),
    "check_trip": Tool(CheckTripArgs, check, "Checking trip"),
    "web_search": Tool(WebSearchArgs, web_search, "Searching the web"),
    "get_weather": Tool(WeatherArgs, get_weather, "Checking weather"),
    "research_city": Tool(ResearchArgs, research_city, "Researching"),
    "remember_preference": Tool(PreferenceArgs, remember_preference, "Saving preference"),
    "request_approval": Tool(ApprovalArgs, None, "Requesting approval"),
}


def _schema(name: str, t: Tool) -> dict:
    schema = t.args.model_json_schema()
    schema.pop("title", None)
    description = t.description or schema.pop("description")
    schema.pop("description", None)
    return {"name": name, "description": description, "input_schema": schema}


TOOL_SCHEMAS = [_schema(name, t) for name, t in TOOLS.items()]


def label(name: str, args: dict) -> str:
    base = TOOLS[name].label if name in TOOLS else name
    detail = next((str(args[k]) for k in ("query", "city", "near", "date") if args.get(k)), "")
    if args.get("queries"):
        detail = ", ".join(map(str, args["queries"]))
    if name == "search_flights":
        detail = " → ".join(str(args[k]) for k in ("origin", "destination") if args.get(k))
    return f"{base} {detail}".strip()


def summarize(result: Any) -> str:
    if isinstance(result, list):
        return f"{len(result)} results"
    if isinstance(result, dict) and "brief" in result:
        return f"brief + {len(result['places'])} places"
    if isinstance(result, dict) and "issues" in result:
        errors = sum(i["severity"] == "error" for i in result["issues"])
        return f"{errors} errors, {len(result['issues']) - errors} warnings"
    text = result if isinstance(result, str) else "done"
    return text if len(text) <= 80 else text[:77] + "…"


def _error_text(e: Exception) -> str:
    if isinstance(e, ValidationError):
        return "; ".join(
            f"{'.'.join(map(str, err['loc'])) or 'args'}: {err['msg']}" for err in e.errors()
        )
    if isinstance(e, NotImplementedError):
        return "This tool is not available yet"
    return str(e) or type(e).__name__


# Tools that never edit the trip: they only add entries to the LOOKUPS dicts, so a
# batch of them can run concurrently (graph.tools merges their updates).
READ_ONLY = {
    "search_flights", "search_hotels", "search_places", "get_place_details",
    "web_search", "get_weather", "research_city",
}
LOOKUPS = {"places", "flight_options", "hotel_options"}


async def run_tool(state: dict, name: str, args: dict) -> tuple[bool, Any, dict]:
    """(ok, result, state_updates). Never raises: failures become an error result."""
    t = TOOLS.get(name)
    if t is None or t.handler is None:
        return False, f"Unknown tool {name!r}", {}
    try:
        parsed = t.args.model_validate(args)
        kwargs = {k: v for k, v in parsed if v is not None}
        result, updates = await t.handler(state, **kwargs)
        return True, result, updates
    except Exception as e:  # tool failures are reported to the planner, never crash the run
        return False, _error_text(e), {}
