# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture Overview
The system uses a LangGraph StateGraph to orchestrate a multi-agent travel planning workflow. Key components include:

- **Supervisor Agent**: Generates execution plans and routes work to parallel agents.
- **Research, Flights, Hotels, Experiences, Budget, Itinerary, Validator, Booking Agents**: Specialized async functions handling specific travel domain tasks.
- **State Management**: Shared `TravelState` TypedDict with reducers for structured state updates.
- **Checkpointing**: Persistent state via `AsyncPostgresSaver` (production) or `MemorySaver` (development).
- **Conditional Routing**: Fan-out execution, revision loops (max 2), and HITL interrupt before booking.

## Agents
Located in the `agents/` directory:
- `graph.py`: Defines the StateGraph structure and compilation.
- `state.py`: TypedDict definitions and reducer annotations.
- `router.py`: Conditional edge functions for fan-out and revision logic.
- Agent implementations under subdirectories: `supervisor/`, `research/`, `flights/`, `hotels/`, `experiences/`, `budget/`, `itinerary/`, `validator/`, `booking/`, `memory/`.

## Tools
Integration tools in the `tools/` directory:
- Flight and hotel search via SerpApi Google Flights/Hotels.
- Web research via Tavily.
- Weather forecasts via OpenWeatherMap.
- Place discovery via Foursquare.
- Currency conversion via approximate local rates.
- Travel distance calculations via Google Maps.

## Data Layer
- **Database**: Async SQLAlchemy with PostgreSQL (production) or SQLite (development). Tables for trips, itineraries, bookings, and user preferences.
- **Vector Memory**: ChromaDB for storing and retrieving user context embeddings.
- **Caching**: Redis for event streaming and real-time progress delivery.

## Configuration
- Environment variables defined in `.env` (e.g., API keys, `DATABASE_URL`, `HITL_ENABLED`).
- Model configuration per agent in `config/model_config.py`.
- Prompt versioning via `prompts/v1/all_prompts.py`.

## Development Workflow
1. Install dependencies: `uv sync --dev`.
2. Create environment file: `cp .env.example .env`.
3. Run API: `uv run python main.py`.
4. Run UI: `uv run python main.py --ui` (or `uv run streamlit run ui/app.py`).
5. Run tests: `uv run pytest tests/ -v --cov`.
6. Build Docker compose: `docker compose up --build`.

## Testing
- Smoke test: `uv run python test_agent.py`.
- End-to-end test: `uv run python test_e2e.py`.
- Full test suite: `uv run pytest tests/ -v --cov`.

## Project Structure
```
AgenticTripPlanner/
├── agents/          # Agent implementations
├── api/             # FastAPI application
├── tools/           # Integration tools
├── schemas/         # Pydantic models
├── config/          # Settings and model configs
├── db/              # Database layer
├── memory/          # Vector memory (ChromaDB)
├── prompts/         # Versioned prompts
├── observability/   # Logging, tracing, metrics
├── ui/              # Streamlit frontend
└── data/            # Local data (gitignored)
```

</tool>
