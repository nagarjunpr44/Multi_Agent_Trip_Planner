from __future__ import annotations

"""
Core LangGraph graph for AgenticTripPlanner.

Architecture:
  START
    └─ memory_load
         └─ supervisor_node
              └─ [Send() fan-out] ──────────────────────────────────────────┐
                   ├─ research_node  ──────────────────────────────────────┐│
                   ├─ flights_node   ──────────────────────────────────────┤│
                   ├─ hotels_node    ──────────────────────────────────────┤│
                   └─ experiences_node ────────────────────────────────────┘│
                                                                             │
                   (all parallel results merged into state)                  │
                                    ▼                                        │
                             budget_node ◄───────────────────────────────────┘
                                    │
                             itinerary_node ◄── revision loop (score < 0.75,
                                    │            revision_count < 2)
                             validator_node     feedback injected via revision_feedback
                                    │
                              ──────┴──────
                  passed/max revisions     not passed
                             │
                       booking_node  ◄── (interrupt_before in HITL mode)
                             │
                       memory_save
                             │
                           END
"""

import logging
import os
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from agents.booking.agent import booking_node
from agents.budget.agent import budget_node
from agents.experiences.agent import experiences_node
from agents.flights.agent import flights_node
from agents.hotels.agent import hotels_node
from agents.itinerary.agent import itinerary_node
from agents.memory.agent import memory_load_node, memory_save_node
from agents.research.agent import research_node
from agents.router import route_after_supervisor
from agents.state import TravelState
from agents.supervisor.agent import supervisor_node
from agents.validator.agent import validator_node

logger = logging.getLogger(__name__)

# RetryPolicy applied to parallel nodes — automatically retries on transient
# LLM rate limits, API timeouts, and network errors with exponential backoff.
_PARALLEL_RETRY = RetryPolicy(
    initial_interval=1.0,
    backoff_factor=2.0,
    max_interval=60.0,
    max_attempts=3,
)


def _build_graph(checkpointer: Any) -> Any:
    """Construct and compile the StateGraph."""
    builder = StateGraph(TravelState)

    # ── Node registration ──────────────────────────────────────────────────
    builder.add_node("memory_load", memory_load_node)
    builder.add_node("supervisor_node", supervisor_node)

    # Parallel nodes get retry policies for transient failures
    builder.add_node("research_node", research_node, retry_policy=_PARALLEL_RETRY)
    builder.add_node("flights_node", flights_node, retry_policy=_PARALLEL_RETRY)
    builder.add_node("hotels_node", hotels_node, retry_policy=_PARALLEL_RETRY)
    builder.add_node("experiences_node", experiences_node, retry_policy=_PARALLEL_RETRY)

    builder.add_node("budget_node", budget_node)
    builder.add_node("itinerary_node", itinerary_node)
    builder.add_node("validator_node", validator_node)
    builder.add_node("booking_node", booking_node)
    builder.add_node("memory_save", memory_save_node)

    # ── Static edges ───────────────────────────────────────────────────────
    builder.add_edge(START, "memory_load")
    builder.add_edge("memory_load", "supervisor_node")

    # All four parallel nodes converge at budget_node (LangGraph waits for all)
    for parallel_node in ("research_node", "flights_node", "hotels_node", "experiences_node"):
        builder.add_edge(parallel_node, "budget_node")

    builder.add_edge("budget_node", "itinerary_node")
    builder.add_edge("itinerary_node", "validator_node")

    # Booking always proceeds to memory save — static edge, no branching needed
    builder.add_edge("booking_node", "memory_save")
    builder.add_edge("memory_save", END)

    # ── Conditional edges ──────────────────────────────────────────────────
    # Supervisor → parallel fan-out via Send()
    builder.add_conditional_edges(
        "supervisor_node",
        route_after_supervisor,
        # path_map not needed when returning Send() objects
    )

    # Validator dynamically routes itself to itinerary_node or booking_node 
    # natively using the 1.1 Command object returned. No edge declarations needed.

    # ── Compile ────────────────────────────────────────────────────────────
    compile_kwargs: dict[str, Any] = {"checkpointer": checkpointer}

    # HITL: interrupt BEFORE booking so the user can review the plan
    hitl_enabled = os.getenv("HITL_ENABLED", "false").lower() == "true"
    if hitl_enabled:
        compile_kwargs["interrupt_before"] = ["booking_node"]
        logger.info("HITL enabled — graph will pause before booking_node")

    graph = builder.compile(**compile_kwargs)
    return graph


# ---------------------------------------------------------------------------
# Async factory — called once at FastAPI startup
# ---------------------------------------------------------------------------

_graph_instance: Any = None


async def get_graph() -> Any:
    """
    Return the compiled graph singleton. Creates it on first call.
    Uses PostgreSQL checkpointer (with connection pool) when DATABASE_URL is
    configured; falls back to in-memory MemorySaver for local development.
    """
    global _graph_instance
    if _graph_instance is not None:
        return _graph_instance

    checkpointer = await _get_checkpointer()
    _graph_instance = _build_graph(checkpointer)
    logger.info("LangGraph compiled successfully (checkpointer=%s)", type(checkpointer).__name__)
    return _graph_instance


async def _get_checkpointer() -> Any:
    """
    Return a checkpointer for the graph.

    Priority:
    1. AsyncPostgresSaver with AsyncConnectionPool (production, concurrent-safe)
    2. AsyncPostgresSaver with single connection (fallback if psycopg_pool missing)
    3. MemorySaver (local dev / no DATABASE_URL)
    """
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        logger.warning("DATABASE_URL not set — using in-memory MemorySaver (not for production)")
        return MemorySaver()

    # Attempt 1: connection pool (preferred for production)
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        pool = AsyncConnectionPool(
            conninfo=database_url,
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

    # Attempt 2: single connection (fallback)
    try:
        import psycopg
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row

        conn = await psycopg.AsyncConnection.connect(
            database_url, autocommit=True, row_factory=dict_row
        )
        checkpointer = AsyncPostgresSaver(conn)  # type: ignore[arg-type]
        await checkpointer.setup()
        logger.info("AsyncPostgresSaver initialized with single PostgreSQL connection")
        return checkpointer
    except Exception as exc:
        logger.error("Failed to initialize PostgreSQL checkpointer (%s) — falling back to MemorySaver", exc)
        return MemorySaver()


async def reset_graph() -> None:
    """Force recreation of the graph singleton (useful in tests)."""
    global _graph_instance
    _graph_instance = None


# ---------------------------------------------------------------------------
# Synchronous graph for CLI / testing convenience
# ---------------------------------------------------------------------------

def get_graph_sync() -> Any:
    """Build a graph with MemorySaver for synchronous use (CLI, pytest)."""
    return _build_graph(MemorySaver())
