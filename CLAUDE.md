# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Architecture
One planner agent (LangGraph) edits a structured `Trip` document through tools; code validates it.
- `trip_planner/trip/models.py`: the Trip schema. It is the central contract; change it carefully.
- `trip_planner/trip/check.py`: deterministic `check_trip` (closed venues, overlaps, budget, pacing…). No LLM.
- `trip_planner/tools/`: async API clients (SerpApi flights/hotels, places via Apify Google Maps scraper or Google Places, Google Routes, OpenWeatherMap, Tavily), cached via `store`. No LLM.
- `trip_planner/agent/`: graph (`planner → tools → approval`), tool handlers, prompts, research sub-agent (cheap model), `service.py` (public API + event schema), CLI.
- `trip_planner/llm.py`: the only place LLM clients are built. `LLM_PROVIDER` (default openai) + per-task models: planner = gpt-5.5, research = gpt-5.4-mini, judge = gpt-5.5 (Anthropic: Sonnet 5.5 / Haiku 4.5 / Opus 5.5).
- `trip_planner/api/`: FastAPI SSE endpoints; serves the built web UI from `web/out`. `trip_planner/evals/`: eval cases, runner, LLM judge.
- `web/`: Next.js web UI (static export, Tailwind, Motion). `src/lib/types.ts` mirrors the Trip schema and stream events; keep them in sync when `models.py` or the event schema changes.

## Rules
- OpenAI: use the Responses API (tools + reasoning effort are rejected on Chat Completions).
- Claude 5.5 models: never set `temperature`, never force `tool_choice`; structured output uses `method="json_schema"`.
- Build system prompts with `llm.system_message()` (adds Anthropic's cache breakpoint only when needed).
- Keep message history append-only (reasoning/thinking blocks are bound to history).
- Stops must reference places from `search_places`; flights/hotels must come from search results. Never let the LLM invent prices, hours or travel times.
- The system prompt must stay stable (prompt caching). Per-turn context goes in the user message.
- Search tools in `agent/tools.READ_ONLY` run concurrently within a step; they may only add to `LOOKUPS` dicts, never edit the trip.
- Tests must not hit the network: mock HTTP via `tools/http.py`, fake chat models for the graph.

## Commands
- Install: `uv sync`
- API + UI: `uv run python -m trip_planner.api` (build the UI first: `cd web && npm install && npm run build`)
- UI dev server: `cd web && npm run dev` (proxies to the API on :8000); UI lint: `cd web && npm run lint`
- CLI: `uv run python -m trip_planner.agent.cli`
- Tests: `uv run pytest -q`; lint: `uv run ruff check trip_planner`
- Evals (costs credits): `uv run python -m trip_planner.evals.run --limit 3`

## Legacy
The old multi-agent pipeline (`agents/`, `api/`, `tools/`, `ui/`, … at the repo root) is superseded by `trip_planner/` and slated for removal.
