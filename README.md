# ✈️ Trip Planner

A conversational trip planner. You chat with one planner agent, and it builds your trip
as a structured document: flights, a hotel, and day-by-day stops at real places. Each
step is grounded in live data, checked by code, and editable through conversation
("make day 2 more relaxed").

## How it works

```
You ⇄ Chat API (SSE streaming)
         │
   Planner agent — LangGraph (planner → tools → approval), Postgres/SQLite checkpoints
         │
   ┌─────┴──────────────────────────────┐
   Search tools                         Trip-editing tools
   flights · hotels (SerpApi)           update_trip · add/update/remove_stop
   places + hours (Google Places)       select_flight · select_hotel · set_day
   travel times (Google Routes)         check_trip  ← deterministic validator
   weather (OpenWeatherMap)             request_approval  ← pauses for the user
   web search (Tavily)
   research_city  ← Haiku sub-agent: reads many results, returns a short brief
```

- **One agent makes all the decisions.** Flights, hotel and itinerary depend on each
  other, so a single planner owns every choice. The only sub-agent is `research_city`,
  which gathers information and makes no decisions.
- **The trip is a document the agent edits.** Revisions are small edits, not full
  regenerations.
- **Grounded.** A stop can only reference a place returned by `search_places`, and
  flights/hotels can only be picked from real search results. Prices, opening hours
  and travel times come from APIs, never from the model.
- **Code checks the trip.** `check_trip` reports concrete problems: closed venues,
  overlapping stops, too-packed days, over budget, scattered days, arrival
  conflicts. The planner fixes them before presenting the plan.
- **Approval before booking.** `request_approval` interrupts the graph; the user
  approves or asks for changes, and the agent returns booking links (no fake bookings).

### Model routing

| Task | Model | Why |
|---|---|---|
| Planner (decisions, tool loop) | `claude-sonnet-5-5`, effort `medium` | judgment + reliable tool use at a reasonable cost |
| Research sub-agent | `claude-haiku-4-5` | reads lots of search results cheaply and fast |
| Eval judge | `claude-opus-5-5`, effort `high` | low volume, accuracy matters |

All set in `trip_planner/llm.py` and overridable via env (`PLANNER_MODEL`, …). The
system prompt and tools are prompt-cached.

## Quick start

```bash
uv sync
cp .env.example .env      # add ANTHROPIC_API_KEY, SERPAPI_API_KEY, GOOGLE_MAPS_API_KEY, TAVILY_API_KEY, OPENWEATHERMAP_API_KEY
uv run python -m trip_planner.api          # web UI + API on http://127.0.0.1:8000
uv run python -m trip_planner.agent.cli    # or chat in the terminal
```

Google Maps key: enable **Places API (New)** and **Routes API**. Without a Routes key,
travel times fall back to straight-line estimates.

## API

| Method | Path | |
|---|---|---|
| POST | `/trips` | new trip → `{id}` |
| GET | `/trips` | list |
| GET | `/trips/{id}` | trip, messages, pending approval, issues, cost |
| POST | `/trips/{id}/messages` `{text}` | SSE stream of events |
| POST | `/trips/{id}/approval` `{approved, note}` | SSE stream (resume) |
| DELETE | `/trips/{id}` | delete |

Events: `text` (streamed reply), `tool_start` / `tool_end`, `trip` (with issues + cost),
`approval`, `done`, `error`. If `APP_API_KEY` is set, send `Authorization: Bearer <key>`.

## Tests and evals

```bash
uv run pytest -q                                        # unit + graph tests, no network
uv run python -m trip_planner.evals.run --limit 3       # real runs: costs API credits
uv run python -m trip_planner.evals.run --case lisbon-relaxed --no-judge
```

The eval set (`trip_planner/evals/cases.json`) contains 20 realistic requests. Each
run is scored with hard checks (day count, zero `check_trip` errors, budget,
flight/hotel chosen, constraints kept) and an Opus rubric (fit, geography, specificity,
pacing, honesty). Latency and cost are reported per case. Re-run it after any prompt,
tool or model change.

## Layout

```
trip_planner/
  config.py      settings (env)
  llm.py         model routing
  store.py       trips index, preferences, tool cache (SQLAlchemy async)
  trip/          Trip schema, check_trip, geo helpers   (pure code)
  tools/         async API clients, cached               (no LLM)
  agent/         LangGraph planner, tools, prompts, research sub-agent, CLI
  api/           FastAPI + static web UI
  evals/         cases, runner, judge
  tests/
```

## Docker

```bash
docker compose up --build     # Postgres + API on :8000
```
