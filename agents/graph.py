"""
Core LangGraph graph for AgenticTripPlanner.

Autonomous architecture:
  START → memory_load → supervisor → [parallel gather] → coverage (loop if gaps)
       → budget → itinerary → itinerary_enrich → validator → orchestrator
       → (enrich | rebuild | re-gather | book) → memory_save → END
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from agents.booking.agent import booking_node
from agents.budget.agent import budget_node
from agents.coverage.agent import coverage_node
from agents.experiences.agent import experiences_node
from agents.flights.agent import flights_node
from agents.hotels.agent import hotels_node
from agents.itinerary.agent import itinerary_node
from agents.itinerary.enrich import itinerary_enrich_node
from agents.memory.agent import memory_load_node, memory_save_node
from agents.orchestrator.agent import orchestrator_node
from agents.research.agent import research_node
from agents.router import route_after_supervisor
from agents.state import TravelState
from agents.supervisor.agent import supervisor_node
from agents.validator.agent import validator_node
from config.settings import get_settings

logger = logging.getLogger(__name__)

_PARALLEL_RETRY = RetryPolicy(
    initial_interval=1.0,
    backoff_factor=2.0,
    max_interval=60.0,
    max_attempts=3,
)


def _build_graph(checkpointer: Any) -> Any:
    builder = StateGraph(TravelState)

    builder.add_node("memory_load", memory_load_node)
    builder.add_node("supervisor_node", supervisor_node)

    builder.add_node("research_node", research_node, retry_policy=_PARALLEL_RETRY)
    builder.add_node("flights_node", flights_node, retry_policy=_PARALLEL_RETRY)
    builder.add_node("hotels_node", hotels_node, retry_policy=_PARALLEL_RETRY)
    builder.add_node("experiences_node", experiences_node, retry_policy=_PARALLEL_RETRY)

    builder.add_node("coverage_node", coverage_node)
    builder.add_node("budget_node", budget_node)
    builder.add_node("itinerary_node", itinerary_node)
    builder.add_node("itinerary_enrich_node", itinerary_enrich_node)
    builder.add_node("validator_node", validator_node)
    builder.add_node("orchestrator_node", orchestrator_node)
    builder.add_node("booking_node", booking_node)
    builder.add_node("memory_save", memory_save_node)

    builder.add_edge(START, "memory_load")
    builder.add_edge("memory_load", "supervisor_node")

    # Parallel gather → autonomous coverage gate (may re-dispatch gather agents)
    for parallel_node in ("research_node", "flights_node", "hotels_node", "experiences_node"):
        builder.add_edge(parallel_node, "coverage_node")

    builder.add_edge("budget_node", "itinerary_node")
    builder.add_edge("itinerary_node", "itinerary_enrich_node")
    builder.add_edge("itinerary_enrich_node", "validator_node")
    builder.add_edge("validator_node", "orchestrator_node")

    builder.add_edge("booking_node", "memory_save")
    builder.add_edge("memory_save", END)

    builder.add_conditional_edges("supervisor_node", route_after_supervisor)

    # coverage_node and orchestrator_node return Command for autonomous routing

    compile_kwargs: dict[str, Any] = {"checkpointer": checkpointer}
    hitl_enabled = get_settings().app.hitl_enabled
    if hitl_enabled:
        compile_kwargs["interrupt_before"] = ["booking_node"]
        logger.info("HITL enabled — graph will pause before booking_node")

    graph = builder.compile(**compile_kwargs)
    return graph


_graph_instance: Any = None


async def get_graph() -> Any:
    global _graph_instance
    if _graph_instance is not None:
        return _graph_instance

    checkpointer = await _get_checkpointer()
    _graph_instance = _build_graph(checkpointer)
    logger.info("LangGraph compiled successfully (checkpointer=%s)", type(checkpointer).__name__)
    return _graph_instance


async def _get_checkpointer() -> Any:
    settings = get_settings()
    checkpoint_url = settings.db.checkpoint_db_url
    if not checkpoint_url:
        logger.warning("CHECKPOINT_DB_URL not set — using in-memory MemorySaver")
        return MemorySaver()

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        pool = AsyncConnectionPool(
            conninfo=checkpoint_url,
            max_size=10,
            kwargs={"autocommit": True, "row_factory": dict_row},
            open=False,
        )
        await pool.open()
        checkpointer = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
        await checkpointer.setup()
        logger.info("AsyncPostgresSaver initialized with connection pool (max_size=10)")
        return checkpointer
    except ImportError:
        logger.warning(
            "psycopg_pool not available — falling back to single connection. "
            "Add psycopg[pool] to dependencies for production use."
        )
    except Exception as exc:
        logger.error("Connection pool setup failed (%s) — trying single connection", exc)

    try:
        import psycopg
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row

        conn = await psycopg.AsyncConnection.connect(
            checkpoint_url, autocommit=True, row_factory=dict_row
        )
        checkpointer = AsyncPostgresSaver(conn)  # type: ignore[arg-type]
        await checkpointer.setup()
        logger.info("AsyncPostgresSaver initialized with single PostgreSQL connection")
        return checkpointer
    except Exception as exc:
        logger.error(
            "Failed to initialize PostgreSQL checkpointer (%s) — falling back to MemorySaver",
            exc,
        )
        return MemorySaver()


async def reset_graph() -> None:
    global _graph_instance
    _graph_instance = None


def get_graph_sync() -> Any:
    return _build_graph(MemorySaver())
