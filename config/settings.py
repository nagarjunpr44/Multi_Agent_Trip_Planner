from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")

    supervisor_model: str = Field(default="gpt-4o", alias="SUPERVISOR_MODEL")
    fast_model: str = Field(default="gpt-4o-mini", alias="FAST_MODEL")
    validator_model: str = Field(default="gpt-4o", alias="VALIDATOR_MODEL")
    prompt_version: str = Field(default="v1", alias="PROMPT_VERSION")


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/agentictripplanner",
        alias="DATABASE_URL",
    )
    checkpoint_db_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/agentictripplanner",
        alias="CHECKPOINT_DB_URL",
    )


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    redis_stream_ttl_seconds: int = Field(default=3600, alias="REDIS_STREAM_TTL_SECONDS")


class ChromaSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    chroma_host: str = Field(default="localhost", alias="CHROMA_HOST")
    chroma_port: int = Field(default=8001, alias="CHROMA_PORT")
    chroma_collection_trip_memory: str = Field(
        default="trip_memory", alias="CHROMA_COLLECTION_TRIP_MEMORY"
    )


class APIKeySettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    serpapi_api_key: str = Field(default="", alias="SERPAPI_API_KEY")
    openweathermap_api_key: str = Field(default="", alias="OPENWEATHERMAP_API_KEY")
    foursquare_api_key: str = Field(default="", alias="FOURSQUARE_API_KEY")
    google_maps_api_key: str = Field(default="", alias="GOOGLE_MAPS_API_KEY")
    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")
    exchange_rates_api_key: str = Field(default="", alias="EXCHANGE_RATES_API_KEY")
    tripadvisor_api_key: str = Field(default="", alias="TRIPADVISOR_API_KEY")
    langsmith_api_key: str = Field(default="", alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(
        default="agentictripplanner", alias="LANGSMITH_PROJECT"
    )
    langsmith_tracing: bool = Field(default=False, alias="LANGSMITH_TRACING")


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "production"] = Field(
        default="development", alias="APP_ENV"
    )
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    app_log_level: str = Field(default="INFO", alias="APP_LOG_LEVEL")

    mcp_enabled: bool = Field(default=False, alias="MCP_ENABLED")
    tool_max_retries: int = Field(default=3, alias="TOOL_MAX_RETRIES")
    tool_timeout_seconds: int = Field(default=30, alias="TOOL_TIMEOUT_SECONDS")
    max_revision_cycles: int = Field(default=2, alias="MAX_REVISION_CYCLES")
    validator_pass_threshold: float = Field(
        default=0.75, alias="VALIDATOR_PASS_THRESHOLD"
    )
    max_graph_steps: int = Field(default=50, alias="MAX_GRAPH_STEPS")
    fastapi_base_url: str = Field(
        default="http://localhost:8000", alias="FASTAPI_BASE_URL"
    )

    @field_validator("app_log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"log level must be one of {valid}")
        return v.upper()


class Settings(BaseSettings):
    """Unified settings — composes all sub-settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm: LLMSettings = Field(default_factory=LLMSettings)
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    chroma: ChromaSettings = Field(default_factory=ChromaSettings)
    apis: APIKeySettings = Field(default_factory=APIKeySettings)
    app: AppSettings = Field(default_factory=AppSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
