"""Settings and per-task model routing."""

from __future__ import annotations

from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Export .env into os.environ too, so LangSmith and the Anthropic SDK see it.
load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    # ── Model routing: one model per kind of task ──────────────────────────
    # planner: owns every decision and edits the trip (needs judgment + tool use)
    planner_model: str = Field("claude-sonnet-5-5", alias="PLANNER_MODEL")
    planner_effort: str = Field("medium", alias="PLANNER_EFFORT")
    # research: reads lots of search results and writes a short brief (cheap, fast)
    research_model: str = Field("claude-haiku-4-5", alias="RESEARCH_MODEL")
    # summary: tiny jobs like titling a trip (cheap, fast)
    summary_model: str = Field("claude-haiku-4-5", alias="SUMMARY_MODEL")
    # judge: grades eval runs (low volume, accuracy matters)
    judge_model: str = Field("claude-opus-5-5", alias="JUDGE_MODEL")
    judge_effort: str = Field("high", alias="JUDGE_EFFORT")

    anthropic_api_key: str = Field("", alias="ANTHROPIC_API_KEY")

    # ── Data APIs ───────────────────────────────────────────────────────────
    serpapi_api_key: str = Field("", alias="SERPAPI_API_KEY")
    google_maps_api_key: str = Field("", alias="GOOGLE_MAPS_API_KEY")
    google_places_api_key: str = Field("", alias="GOOGLE_PLACES_API_KEY")
    openweathermap_api_key: str = Field("", alias="OPENWEATHERMAP_API_KEY")
    tavily_api_key: str = Field("", alias="TAVILY_API_KEY")
    tool_timeout_seconds: float = Field(20.0, alias="TOOL_TIMEOUT_SECONDS")
    cache_ttl_hours: float = Field(12.0, alias="CACHE_TTL_HOURS")

    # ── Storage ─────────────────────────────────────────────────────────────
    # App tables (trips index, preferences, tool cache).
    app_db_url: str = Field("sqlite+aiosqlite:///./data/trip_planner.db", alias="APP_DB_URL")
    # LangGraph checkpoints. Empty → SQLite file; postgresql://... → Postgres.
    checkpoint_url: str = Field("", alias="CHECKPOINT_URL")

    # ── API ─────────────────────────────────────────────────────────────────
    app_api_key: str = Field("", alias="APP_API_KEY")  # empty = no auth (local dev)
    rate_limit_per_minute: int = Field(20, alias="RATE_LIMIT_PER_MINUTE")
    host: str = Field("127.0.0.1", alias="HOST")
    port: int = Field(8000, alias="PORT")

    @property
    def places_key(self) -> str:
        return self.google_places_api_key or self.google_maps_api_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
