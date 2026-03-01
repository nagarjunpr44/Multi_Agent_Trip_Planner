# ✈️ AgenticTripPlanner

**Production-grade AI travel planning system powered by LangGraph multi-agent orchestration.**

AgenticTripPlanner is a full-stack application that uses a team of specialized AI agents — coordinated via a LangGraph `StateGraph` — to research destinations, search flights and hotels, discover local experiences, optimize budgets, build day-by-day itineraries, validate plan quality, and handle simulated bookings. It features a FastAPI backend, Streamlit chat UI, real-time SSE/WebSocket streaming, Human-in-the-Loop (HITL) approval, persistent memory via ChromaDB, and full observability with Prometheus + LangSmith.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [LangGraph Structure](#langgraph-structure)
  - [Graph Topology](#graph-topology)
  - [State Schema](#state-schema)
  - [Conditional Routing](#conditional-routing)
  - [Checkpointing](#checkpointing)
- [Agents](#agents)
  - [Supervisor Agent](#1-supervisor-agent)
  - [Research Agent](#2-research-agent)
  - [Flights Agent](#3-flights-agent)
  - [Hotels Agent](#4-hotels-agent)
  - [Experiences Agent](#5-experiences-agent)
  - [Budget Agent](#6-budget-agent)
  - [Itinerary Agent](#7-itinerary-agent)
  - [Validator Agent](#8-validator-agent)
  - [Booking Agent](#9-booking-agent)
  - [Memory Agents](#10-memory-agents-load--save)
- [Tools](#tools)
- [API Layer](#api-layer)
  - [Endpoints](#endpoints)
  - [Real-Time Streaming](#real-time-streaming-sse--websocket)
  - [Human-in-the-Loop (HITL)](#human-in-the-loop-hitl)
- [Streamlit UI](#streamlit-ui)
- [Data Layer](#data-layer)
  - [PostgreSQL / SQLite](#postgresql--sqlite)
  - [Redis](#redis)
  - [ChromaDB (Vector Memory)](#chromadb-vector-memory)
- [Schemas](#schemas)
- [Configuration](#configuration)
  - [Environment Variables](#environment-variables)
  - [Model Configuration](#model-configuration)
  - [Prompt Versioning](#prompt-versioning)
- [Observability](#observability)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Local Development](#local-development)
  - [Docker Compose (Full Stack)](#docker-compose-full-stack)
  - [Running Tests](#running-tests)
- [Project Structure](#project-structure)

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          Streamlit Chat UI (:8501)                       │
│   Conversational intake  →  Kicks off planning  →  Displays results     │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │ HTTP / SSE / WebSocket
┌─────────────────────────────────▼────────────────────────────────────────┐
│                        FastAPI Backend (:8000)                           │
│  POST /trips           — start async planning run                       │
│  GET  /trips/:id       — poll trip status & results                     │
│  GET  /trips/:id/stream— SSE real-time agent progress                   │
│  WS   /ws/trips/:id    — WebSocket real-time agent progress             │
│  POST /trips/:id/approve — HITL resume with approval                    │
│  POST /trips/:id/reject  — HITL cancel                                  │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │
┌─────────────────────────────────▼────────────────────────────────────────┐
│                      LangGraph StateGraph Engine                         │
│                                                                          │
│  memory_load → supervisor → [parallel fan-out] → budget → itinerary     │
│                                                  → validator → booking   │
│                                                              → memory_save│
│                                                                          │
│  Checkpointer: AsyncPostgresSaver (prod) / MemorySaver (dev)            │
└──────┬──────────┬──────────┬──────────┬──────────┬───────────────────────┘
       │          │          │          │          │
   ┌───▼──┐  ┌───▼──┐  ┌───▼──┐  ┌───▼──┐  ┌───▼───┐
   │Amadeus│  │Tavily│  │Foursq│  │Google│  │OpenWM │
   │Flights│  │Search│  │Places│  │ Maps │  │Weather│
   │Hotels │  │      │  │      │  │      │  │       │
   └───────┘  └──────┘  └──────┘  └──────┘  └───────┘

   ┌───────────────────────────────────────────────┐
   │  PostgreSQL   │   Redis    │    ChromaDB       │
   │  Trip storage │  SSE/Event │  Vector memory    │
   │  Checkpoints  │  streaming │  User preferences │
   └───────────────────────────────────────────────┘
```

---

## LangGraph Structure

The core orchestration engine is a **LangGraph `StateGraph`** defined in `agents/graph.py`. It coordinates 10 agent nodes through a mix of parallel fan-out (via `Send()`), sequential edges, and conditional revision loops.

### Graph Topology

```
START
  └─► memory_load_node
        └─► supervisor_node
              └─► [Send() fan-out] ─────────────────────────────┐
                    ├─ research_node     ───────────────────────┐│
                    ├─ flights_node      ───────────────────────┤│
                    ├─ hotels_node       ───────────────────────┤│
                    └─ experiences_node  ────────────────────────┘│
                                                                  │
                    (all parallel outputs merged into state)      │
                                     ▼                            │
                              budget_node ◄───────────────────────┘
                                     │
                              itinerary_node
                                     │
                              validator_node ─── score < 0.75? ──► budget_node
                                     │              (max 2 revisions)
                                     │ score ≥ 0.75 or max revisions
                                     ▼
                              booking_node  ◄── (interrupt_before in HITL mode)
                                     │
                              memory_save_node
                                     │
                                    END
```

**Key design decisions:**

| Concept | Implementation |
|---|---|
| **Parallel fan-out** | `Send()` objects dispatch the same state snapshot to 4 independent agents simultaneously |
| **Convergence** | All 4 parallel nodes have static edges to `budget_node`; LangGraph waits for all to complete |
| **Revision loop** | Conditional edge from `validator_node` routes back to `budget_node` if score < 0.75 (max 2 loops) |
| **HITL interrupt** | When `HITL_ENABLED=true`, graph compiles with `interrupt_before=["booking_node"]` |
| **Checkpointing** | `AsyncPostgresSaver` for production persistence, `MemorySaver` for local dev |

### State Schema

The shared state (`TravelState` in `agents/state.py`) is a `TypedDict` with reducer annotations:

| Field | Type | Description |
|---|---|---|
| `session_id` | `str` | Unique session identifier |
| `user_query` | `str` | Natural-language trip request |
| `constraints` | `dict` | Parsed `TripConstraints` (budget, dates, destinations, preferences) |
| `mode` | `Literal["autonomous", "hitl"]` | Execution mode |
| `messages` | `Annotated[list[BaseMessage], add_messages]` | Conversation history (LangGraph message reducer) |
| `execution_plan` | `list[str]` | Supervisor's ordered execution plan |
| `parallel_targets` | `list[str]` | Which agents to fan out to |
| `supervisor_plan` | `dict` | Full `SupervisorPlan` output |
| `destination_info` | `dict` | Research agent's `DestinationInfo` |
| `flight_results` | `dict` | `FlightSearchResult` from flights agent |
| `hotel_results` | `dict` | `HotelSearchResult` from hotels agent |
| `experience_results` | `list[dict]` | List of `Experience` objects |
| `budget_analysis` | `dict` | 3-tier `BudgetAnalysis` |
| `itinerary` | `dict` | Day-by-day `Itinerary` |
| `validation_result` | `dict` | `ValidationResult` with 4-dimension scoring |
| `booking_result` | `dict` | `BookingResult` with booking reference |
| `user_context` | `dict` | Loaded from ChromaDB (past trips, preferences) |
| `human_feedback` | `str` | User feedback from HITL review |
| `human_approved` | `bool` | HITL approval flag |
| `revision_count` | `int` | Number of validator → budget revision loops |
| `status` | `str` | `queued \| running \| paused_hitl \| complete \| failed` |
| `errors` | `Annotated[list[dict], operator.add]` | Accumulated errors (additive reducer) |
| `agent_timings` | `Annotated[dict[str, float], _merge_dicts]` | Per-agent duration in ms (merge reducer) |

### Conditional Routing

Three conditional edge functions are defined in `agents/router.py`:

1. **`route_after_supervisor`** — Returns a list of `Send()` objects for parallel fan-out. The supervisor populates `parallel_targets`; defaults to all 4 parallel agents.

2. **`route_after_validator`** — If `validation_result.passed == False` and `revision_count < 2`, routes back to `budget_node` for re-planning. Otherwise proceeds to `booking_node`.

3. **`route_after_booking`** — Always routes to `memory_save` to persist trip context.

### Checkpointing

| Environment | Checkpointer | Config |
|---|---|---|
| **Production** | `AsyncPostgresSaver` (PostgreSQL via psycopg3) | `DATABASE_URL` env var |
| **Development** | `MemorySaver` (in-memory) | No `DATABASE_URL` set |

The checkpointer enables:
- **State persistence** across process restarts
- **HITL resume** — the graph pauses, the user reviews via API, then the graph resumes from the saved checkpoint
- **Time-travel debugging** — inspect any intermediate state snapshot

---

## Agents

Each agent is an async function that receives `TravelState`, calls an LLM (with optional tool use), and returns state updates. Agents use **structured output** (function calling) to produce validated Pydantic models.

### 1. Supervisor Agent
**File:** `agents/supervisor/agent.py`
**Model:** `gpt-4o` (temperature 0.3)
**Output:** `SupervisorPlan`

Parses the user query, extracts structured constraints, and produces an execution plan specifying which agents to invoke and which can run in parallel. Uses user memory context (past trips) to inform planning.

### 2. Research Agent
**File:** `agents/research/agent.py`
**Model:** `gpt-4o-mini` (temperature 0.5)
**Tools:** `web_research_tool`, `get_weather_tool`
**Output:** `DestinationInfo`

Gathers destination intelligence via Tavily web search and OpenWeatherMap weather API. Runs a tool-calling loop (max 3 iterations), then synthesizes results into a structured `DestinationInfo` with highlights, cultural tips, visa info, weather forecasts, and local recommendations.

### 3. Flights Agent
**File:** `agents/flights/agent.py`
**Model:** `gpt-4o-mini` (temperature 0.1)
**Tools:** `search_flights_tool`
**Output:** `FlightSearchResult`

Searches for flight options using the Amadeus Flight Offers API. The LLM infers IATA codes from city names, calls the search tool, and the results are parsed into structured `FlightOption` objects with price, duration, stops, and baggage info. Falls back to mock data if the API is unavailable.

### 4. Hotels Agent
**File:** `agents/hotels/agent.py`
**Model:** `gpt-4o-mini` (temperature 0.1)
**Tools:** `search_hotels_tool`
**Output:** `HotelSearchResult`

Searches for hotel accommodations using the Amadeus Hotel API (city listing → offer search). Returns options with star ratings, pricing, amenities, and refundability. Falls back to tiered mock data if needed.

### 5. Experiences Agent
**File:** `agents/experiences/agent.py`
**Model:** `gpt-4o-mini` (temperature 0.6)
**Tools:** `search_places_tool`
**Output:** `list[Experience]`

Discovers restaurants, attractions, hidden gems, and activities using the Foursquare Places API. Searches across 4 categories with up to 8 tool-calling iterations. Respects dietary restrictions and activity preferences from constraints.

### 6. Budget Agent
**File:** `agents/budget/agent.py`
**Model:** `gpt-4o-mini` (temperature 0.1)
**Tools:** `convert_currency_tool`
**Output:** `BudgetAnalysis`

Synthesizes cost data from flights, hotels, and experiences into a 3-tier budget analysis (budget / mid / luxury). Each tier breaks down costs by category (flights, hotels, activities, food, transport, miscellaneous). Includes per-person-per-day estimates and money-saving tips. Performs currency conversion for non-USD destinations.

### 7. Itinerary Agent
**File:** `agents/itinerary/agent.py`
**Model:** `gpt-4o` (temperature 0.7, max 8192 tokens)
**Tools:** `get_travel_distance_tool`
**Output:** `Itinerary`

Builds a complete day-by-day itinerary using all gathered data. Calls the Google Maps Distance Matrix API to get realistic travel times between activities. Each `DayPlan` has morning/afternoon/evening blocks with 3–5 activities, cost estimates, and practical notes. Backfills dates if the LLM leaves them empty.

### 8. Validator Agent
**File:** `agents/validator/agent.py`
**Model:** `gpt-4o` (temperature 0.0)
**Output:** `ValidationResult`

Quality-critics the complete plan across 4 dimensions:
- **Feasibility** — realistic timing and logistics
- **Budget Alignment** — matches user's stated budget
- **Coverage** — addresses all user preferences
- **Quality** — specific, curated, includes hidden gems

Overall score is the average. **Pass threshold = 0.75**. If failed, provides specific issues and suggestions. The graph loops back to `budget_node` for re-planning (max 2 revision cycles).

### 9. Booking Agent
**File:** `agents/booking/agent.py`
**Model:** `gpt-4o-mini` (temperature 0.0)
**Output:** `BookingResult`

HITL interrupt point. In **autonomous mode**, proceeds directly with mock booking confirmation. In **HITL mode**, the graph pauses before this node; the user reviews the plan via the API and approves/rejects. Generates a booking reference, confirms flight/hotel selections, and stamps total charged amount.

### 10. Memory Agents (Load & Save)
**File:** `agents/memory/agent.py`

- **`memory_load_node`** — Runs at graph START. Queries ChromaDB for relevant past trip summaries matching the current query. Returns `user_context` with past trips and preferences to enrich the supervisor's planning.

- **`memory_save_node`** — Runs at graph END. Embeds a completed trip summary into ChromaDB for future retrieval. Uses OpenAI `text-embedding-3-small` for embeddings.

---

## Tools

All tools are LangChain `@tool`-decorated async functions registered in a central `ToolRegistry` (`tools/registry.py`). Each tool has automatic retry with exponential backoff via `tenacity`. Every tool falls back to mock data when `MOCK_FALLBACK=true` or when the real API key is missing.

| Tool | File | API | Description |
|---|---|---|---|
| `search_flights_tool` | `tools/flights.py` | Amadeus Flight Offers | Search flights by origin/destination/dates |
| `search_hotels_tool` | `tools/hotels.py` | Amadeus Hotel Offers | Search hotels by city/dates/guests |
| `search_places_tool` | `tools/places.py` | Foursquare Places v3 | Discover restaurants, attractions, hidden gems |
| `web_research_tool` | `tools/research.py` | Tavily Search | Web search for destination intelligence |
| `get_weather_tool` | `tools/weather.py` | OpenWeatherMap | Weather forecasts for destinations |
| `convert_currency_tool` | `tools/currency.py` | Open Exchange Rates | Currency conversion between codes |
| `get_travel_distance_tool` | `tools/maps.py` | Google Distance Matrix | Travel time/distance between locations |

**Agent → Tool mapping:**

| Agent | Tools |
|---|---|
| Research | `web_research_tool`, `get_weather_tool` |
| Flights | `search_flights_tool` |
| Hotels | `search_hotels_tool` |
| Experiences | `search_places_tool` |
| Budget | `convert_currency_tool` |
| Itinerary | `get_travel_distance_tool` |
| Booking | `search_flights_tool`, `search_hotels_tool` |
| Supervisor, Validator, Memory | (no tools) |

---

## API Layer

The FastAPI application (`api/app.py`) is created with a lifespan handler that:
1. Creates database tables (SQLite or PostgreSQL)
2. Initializes Redis connection
3. Registers all tools in the `ToolRegistry`
4. Pre-warms the LangGraph compilation and checkpointer

### Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/trips` | Start async trip planning (returns 202 with `session_id`) |
| `GET` | `/trips` | List all trips (paginated) |
| `GET` | `/trips/{session_id}` | Get trip status, itinerary, booking, raw state |
| `DELETE` | `/trips/{session_id}` | Delete a trip |
| `GET` | `/trips/{session_id}/stream` | SSE endpoint for real-time agent progress |
| `WS` | `/ws/trips/{session_id}` | WebSocket endpoint for real-time events |
| `POST` | `/trips/{session_id}/approve` | HITL: resume graph with approval + optional feedback |
| `POST` | `/trips/{session_id}/reject` | HITL: cancel the planning run |
| `GET` | `/health` | Basic health check |
| `GET` | `/health/ready` | Readiness check (Redis + Postgres connectivity) |
| `GET` | `/metrics` | Prometheus metrics (if `prometheus_client` installed) |
| `GET` | `/docs` | Swagger UI |
| `GET` | `/redoc` | ReDoc API docs |

### Real-Time Streaming (SSE & WebSocket)

When a trip is started via `POST /trips`, the LangGraph runs as a **background task**. Agent progress events are published to a **Redis Stream** (`trip:events:{session_id}`) via `StreamEventPublisher`.

Clients consume events through:
- **SSE** (`GET /trips/{session_id}/stream`) — Server-Sent Events with keep-alive pings
- **WebSocket** (`WS /ws/trips/{session_id}`) — JSON messages with the same event format

Event types: `graph_start`, `agent_start`, `agent_complete`, `graph_complete`, `error`

### Human-in-the-Loop (HITL)

When `HITL_ENABLED=true`:
1. The graph compiles with `interrupt_before=["booking_node"]`
2. After the validator passes, the graph **pauses** before booking
3. Client receives a `hitl_pause` event via SSE/WebSocket
4. User reviews the itinerary and calls:
   - `POST /trips/{session_id}/approve` — injects `human_approved=True` + optional `human_feedback` into state, then resumes the graph
   - `POST /trips/{session_id}/reject` — cancels the run

**Middleware:**
- `RequestIDMiddleware` — attaches `X-Request-ID` to every request/response with timing headers
- `CORSMiddleware` — allows all origins (configurable for production)

---

## Streamlit UI

**File:** `ui/app.py`  
**Pages:** `ui/pages/plan_trip.py`, `ui/pages/my_trips.py`

The UI provides a **conversational chat interface** powered by a **TravelBot intake agent** (GPT-4o-mini via the OpenAI SDK directly):

1. **Chat & Plan** — The user describes their trip in natural language. TravelBot asks clarifying questions (2–3 max), then emits a hidden JSON handoff block parsed by the frontend.
2. The frontend extracts constraints and calls `POST /trips` on the FastAPI backend.
3. SSE is consumed to show real-time agent progress with animated status indicators.
4. Final itinerary, budget, and booking are displayed with rich formatting.

**My Trips** — Browse past planning sessions, view details, and delete trips.

---

## Data Layer

### PostgreSQL / SQLite

**Connection:** `db/connection.py` — async SQLAlchemy engine with connection pooling.  
**Models:** `db/models.py` — 4 tables:

| Table | Purpose |
|---|---|
| `trips` | Main trip record (query, constraints, status, itinerary JSON, booking JSON, raw state) |
| `itinerary_records` | Versioned itinerary snapshots (linked to trip) |
| `booking_records` | Individual booking line items (flight, hotel, activity) |
| `user_preferences` | Key-value preferences with optional embedding IDs |

**Repository:** `db/repository.py` — CRUD operations (`TripRepository`) with JSON-safe serialization.  
**Migrations:** Alembic (`alembic.ini`, `db/migrations/`) for schema evolution.

- **Production:** PostgreSQL 16 via `asyncpg`
- **Development:** SQLite via `aiosqlite` (auto-created)

### Redis

**File:** `cache/redis_client.py`

Redis 7 is used for:
- **Stream-based event publishing** — `StreamEventPublisher` writes to Redis Streams (`XADD`)
- **SSE/WebSocket consumption** — `XREAD` with blocking reads
- **TTL management** — streams auto-expire (default 1 hour)

Redis is **optional** — if unavailable, the API still functions but SSE/WS streaming is disabled.

### ChromaDB (Vector Memory)

**Files:** `memory/chroma_store.py`, `memory/context_manager.py`, `memory/embeddings.py`

- **Embeddings:** OpenAI `text-embedding-3-small` via `langchain-openai`
- **Storage:** ChromaDB collection `trip_memory` with cosine similarity
- **Load:** At graph start, queries for past trip summaries relevant to the current request (distance < 0.6)
- **Save:** At graph end, embeds and upserts a trip summary for future retrieval
- Supports both embedded (local) and HTTP client modes

---

## Schemas

All structured outputs use Pydantic v2 models with `model_validator` for null coercion:

| Schema | File | Used By |
|---|---|---|
| `SupervisorPlan` | `schemas/agent_output.py` | Supervisor agent |
| `DestinationInfo` | `schemas/agent_output.py` | Research agent |
| `ValidationResult` | `schemas/agent_output.py` | Validator agent |
| `BookingResult` | `schemas/agent_output.py` | Booking agent |
| `FlightSearchResult`, `FlightOption`, `FlightSegment` | `schemas/flight.py` | Flights agent/tool |
| `HotelSearchResult`, `HotelOption`, `HotelAmenity` | `schemas/hotel.py` | Hotels agent/tool |
| `BudgetAnalysis`, `BudgetTier`, `CostLineItem` | `schemas/budget.py` | Budget agent |
| `Itinerary`, `DayPlan`, `Activity`, `Experience` | `schemas/itinerary.py` | Itinerary/Experiences agents |
| `TripRequest`, `TripResponse`, `TripConstraints` | `schemas/trip.py` | API layer |

---

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
# ── LLM ──────────────────────────────────────────────
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...          # optional, for Claude models
SUPERVISOR_MODEL=gpt-4o              # or claude-3-5-sonnet-20241022
FAST_MODEL=gpt-4o-mini
VALIDATOR_MODEL=gpt-4o

# ── External APIs ────────────────────────────────────
AMADEUS_API_KEY=...
AMADEUS_API_SECRET=...
AMADEUS_HOSTNAME=test                # test | production
TAVILY_API_KEY=tvly-...
OPENWEATHERMAP_API_KEY=...
FOURSQUARE_API_KEY=...
GOOGLE_MAPS_API_KEY=...
EXCHANGE_RATES_API_KEY=...

# ── Infrastructure ───────────────────────────────────
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/agentictripplanner
REDIS_URL=redis://localhost:6379/0
CHROMA_HOST=localhost
CHROMA_PORT=8001

# ── App Settings ─────────────────────────────────────
APP_ENV=development                  # development | production
MOCK_FALLBACK=false                  # true = use mock data for all tools
HITL_ENABLED=false                   # true = pause before booking
MAX_REVISION_CYCLES=2
VALIDATOR_PASS_THRESHOLD=0.75

# ── Observability ────────────────────────────────────
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2-...
LANGCHAIN_PROJECT=AgenticTripPlanner
LOG_LEVEL=INFO
```

### Model Configuration

Each agent has its own model config (`config/model_config.py`):

| Agent | Model | Temperature | Max Tokens | Notes |
|---|---|---|---|---|
| Supervisor | `SUPERVISOR_MODEL` | 0.3 | 2048 | Strategic planning |
| Research | `FAST_MODEL` | 0.5 | 4096 | Creative research |
| Flights | `FAST_MODEL` | 0.1 | 2048 | Precise tool calling |
| Hotels | `FAST_MODEL` | 0.1 | 2048 | Precise tool calling |
| Experiences | `FAST_MODEL` | 0.6 | 3072 | Creative discovery |
| Budget | `FAST_MODEL` | 0.1 | 2048 | Accurate calculations |
| Itinerary | `SUPERVISOR_MODEL` | 0.7 | 8192 | Creative, detailed output |
| Validator | `VALIDATOR_MODEL` | 0.0 | 1024 | Deterministic scoring |
| Booking | `FAST_MODEL` | 0.0 | 1024 | Deterministic confirmation |

The system auto-detects provider (OpenAI vs Anthropic) based on model name — if `"claude"` appears in the name, `ChatAnthropic` is used; otherwise `ChatOpenAI`.

### Prompt Versioning

Prompts are loaded dynamically via `prompts/loader.py` based on the `PROMPT_VERSION` env var (default: `v1`). All agent system prompts live in `prompts/v1/all_prompts.py` as module-level constants, enabling A/B testing of different prompt strategies by switching the version.

---

## Observability

| Layer | Tool | Details |
|---|---|---|
| **Logging** | `structlog` / stdlib | JSON structured logging in production, pretty-print in dev |
| **Tracing** | LangSmith | Full LangGraph run traces with every LLM call, tool invocation, and state transition |
| **Metrics** | Prometheus | `atp_graph_runs_total`, `atp_agent_duration_seconds`, `atp_active_sessions`, `atp_validation_score` |
| **Agent Timings** | Built-in | Every agent records `duration_ms` into `agent_timings` state field |
| **Request Tracking** | Middleware | `X-Request-ID` and `X-Response-Time-Ms` on every HTTP response |

The `/metrics` endpoint is auto-mounted when `prometheus_client` is installed.

---

## Getting Started

### Prerequisites

- **Python 3.11+**
- **OpenAI API key** (required)
- **Docker + Docker Compose** (optional, for full-stack deployment)

### Local Development

```bash
# 1. Clone and setup
cd AgenticTripPlanner
python -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Configure environment
cp .env.example .env   # Edit with your API keys

# 4. Run the smoke test (no external services needed)
MOCK_FALLBACK=true python test_agent.py

# 5. Start the API server
python main.py

# 6. Start the Streamlit UI (separate terminal)
python main.py --ui
# Or directly:
streamlit run ui/app.py
```

The API runs on `http://localhost:8000` (Swagger docs at `/docs`).  
The UI runs on `http://localhost:8501`.

> **Note:** Without `DATABASE_URL`, the app uses SQLite + in-memory checkpointing. Without Redis, SSE/WebSocket streaming is disabled but the API still works.

### Docker Compose (Full Stack)

```bash
# Start all services: PostgreSQL, Redis, ChromaDB, API, UI
docker compose up --build

# Services:
#   API:      http://localhost:8000
#   UI:       http://localhost:8501
#   Postgres: localhost:5432
#   Redis:    localhost:6379
#   ChromaDB: localhost:8001
```

### Running Tests

```bash
# Smoke test (mock mode, no services needed)
MOCK_FALLBACK=true python test_agent.py

# End-to-end test (uses real APIs if configured)
python test_e2e.py

# Pytest suite
pytest tests/ -v --cov

# Run database migrations
python main.py --migrate
```

---

## Project Structure

```
AgenticTripPlanner/
├── main.py                        # Entrypoint: API server, UI, or migrations
├── pyproject.toml                 # Dependencies and project metadata
├── Dockerfile                     # Container image (Python 3.12-slim)
├── docker-compose.yml             # Full stack: Postgres, Redis, ChromaDB, API, UI
├── alembic.ini                    # Alembic migration config
├── test_agent.py                  # Smoke test (mock mode)
├── test_e2e.py                    # End-to-end test with rich output
│
├── agents/                        # LangGraph agent nodes
│   ├── graph.py                   # StateGraph definition, compilation, checkpointer
│   ├── state.py                   # TravelState TypedDict with reducers
│   ├── router.py                  # Conditional edge functions (fan-out, revision loop)
│   ├── llm_factory.py             # LLM instantiation (OpenAI / Anthropic)
│   ├── supervisor/agent.py        # Orchestrator — parses query, produces execution plan
│   ├── research/agent.py          # Destination intelligence (Tavily + weather)
│   ├── flights/agent.py           # Flight search (Amadeus)
│   ├── hotels/agent.py            # Hotel search (Amadeus)
│   ├── experiences/agent.py       # Places discovery (Foursquare)
│   ├── budget/agent.py            # 3-tier budget analysis + currency conversion
│   ├── itinerary/agent.py         # Day-by-day itinerary builder (+ distance API)
│   ├── validator/agent.py         # Quality critic — 4-dimension scoring
│   ├── booking/agent.py           # Mock booking + HITL interrupt point
│   └── memory/agent.py            # ChromaDB load/save for user preferences
│
├── api/                           # FastAPI application
│   ├── app.py                     # App factory + lifespan handler
│   ├── dependencies.py            # Dependency injection (DB, Redis, Graph)
│   ├── middleware.py               # Request ID + timing middleware
│   └── routes/
│       ├── planning.py            # POST /trips — start async planning
│       ├── trips.py               # GET/DELETE /trips — CRUD
│       ├── streaming.py           # GET /trips/:id/stream — SSE
│       ├── websocket.py           # WS /ws/trips/:id — WebSocket
│       ├── hitl.py                # POST /trips/:id/approve|reject
│       └── health.py             # Health + readiness checks
│
├── tools/                         # LangChain tool functions
│   ├── registry.py                # Central tool registry + agent-tool mapping
│   ├── flights.py                 # Amadeus flight search + mock
│   ├── hotels.py                  # Amadeus hotel search + mock
│   ├── places.py                  # Foursquare places search + mock
│   ├── research.py                # Tavily web search + mock
│   ├── weather.py                 # OpenWeatherMap forecast + mock
│   ├── currency.py                # Exchange rate conversion + mock
│   └── maps.py                    # Google Distance Matrix + mock
│
├── schemas/                       # Pydantic v2 models
│   ├── agent_output.py            # SupervisorPlan, DestinationInfo, ValidationResult, BookingResult
│   ├── flight.py                  # FlightSearchResult, FlightOption, FlightSegment
│   ├── hotel.py                   # HotelSearchResult, HotelOption, HotelAmenity
│   ├── budget.py                  # BudgetAnalysis, BudgetTier, CostLineItem
│   ├── itinerary.py               # Itinerary, DayPlan, Activity, Experience
│   └── trip.py                    # TripRequest, TripResponse, TripConstraints
│
├── config/                        # Configuration
│   ├── settings.py                # Pydantic Settings (LLM, DB, Redis, APIs, App)
│   └── model_config.py            # Per-agent model registry (model, temp, tokens)
│
├── db/                            # Database layer
│   ├── connection.py              # Async SQLAlchemy engine + session factory
│   ├── models.py                  # ORM models (Trip, ItineraryRecord, BookingRecord)
│   ├── repository.py              # TripRepository CRUD operations
│   └── migrations/                # Alembic migrations
│
├── memory/                        # Vector memory (ChromaDB)
│   ├── chroma_store.py            # TripMemoryStore — upsert/query/delete
│   ├── context_manager.py         # ContextManager — high-level load/save
│   └── embeddings.py              # OpenAI text-embedding-3-small
│
├── cache/
│   └── redis_client.py            # Redis init, StreamEventPublisher, SSE bridge
│
├── prompts/                       # Versioned agent prompts
│   ├── loader.py                  # Dynamic prompt loading by version
│   └── v1/all_prompts.py          # All agent system prompts (v1)
│
├── observability/                 # Logging, tracing, metrics
│   ├── logging.py                 # Structured logging (structlog + stdlib)
│   ├── tracing.py                 # LangSmith tracing setup
│   └── metrics.py                 # Prometheus counters, histograms, gauges
│
├── ui/                            # Streamlit frontend
│   ├── app.py                     # Main Streamlit app + sidebar navigation
│   ├── pages/
│   │   ├── plan_trip.py           # Chat-based trip planning with live agent status
│   │   └── my_trips.py            # Browse and manage past trips
│   └── components/
│       └── hitl.py                # HITL approval UI components
│
└── data/                          # Local data (gitignored)
    ├── chromadb/                   # ChromaDB persistent storage
    ├── logs/                       # Application logs
    ├── sessions/                   # Session data
    └── workspace/                  # Temporary workspace
```

