from __future__ import annotations

"""
Core LangGraph graph for AgenticTripPlanner.

Architecture:
  START
    └─ memory_load_node
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
                                    │      (revision loop if score < 0.75
                             itinerary_node   and revision_count < 2)
                                    │
                             validator_node ──► booking_node (if passed or max revisions)
                                                      │ (interrupt_before in HITL mode)
                                               memory_save_node
                                                      │
                                                    END
"""

import logging
import os
from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from agents.state import TravelState
from agents.supervisor.agent import supervisor_node
from agents.research.agent import research_node
from agents.flights.agent import flights_node
from agents.hotels.agent import hotels_node
from agents.experiences.agent import experiences_node
from agents.budget.agent import budget_node
from agents.itinerary.agent import itinerary_node
from agents.validator.agent import validator_node
from agents.booking.agent import booking_node
from agents.memory.agent import memory_load_node, memory_save_node
from agents.router import route_after_supervisor, route_after_validator, route_after_booking

logger = logging.getLogger(__name__)


def _build_graph(checkpointer: Any) -> Any:
    """Construct and compile the StateGraph."""
    builder = StateGraph(TravelState)

    # ── Node registration ──────────────────────────────────────────────────
    builder.add_node("memory_load", memory_load_node)
    builder.add_node("supervisor_node", supervisor_node)
    builder.add_node("research_node", research_node)
    builder.add_node("flights_node", flights_node)
    builder.add_node("hotels_node", hotels_node)
    builder.add_node("experiences_node", experiences_node)
    builder.add_node("budget_node", budget_node)
    builder.add_node("itinerary_node", itinerary_node)
    builder.add_node("validator_node", validator_node)
    builder.add_node("booking_node", booking_node)
    builder.add_node("memory_save", memory_save_node)

    # ── Static edges ───────────────────────────────────────────────────────
    builder.add_edge(START, "memory_load")
    builder.add_edge("memory_load", "supervisor_node")

    # After each parallel node, converge to budget
    for parallel_node in ("research_node", "flights_node", "hotels_node", "experiences_node"):
        builder.add_edge(parallel_node, "budget_node")

    builder.add_edge("budget_node", "itinerary_node")
    builder.add_edge("itinerary_node", "validator_node")
    builder.add_edge("memory_save", END)

    # ── Conditional edges ──────────────────────────────────────────────────
    # Supervisor → parallel fan-out via Send()
    builder.add_conditional_edges(
        "supervisor_node",
        route_after_supervisor,
        # path_map not needed when returning Send() objects
    )

    # Validator → revision loop or booking
    builder.add_conditional_edges(
        "validator_node",
        route_after_validator,
        {
            "budget_node": "budget_node",
            "booking_node": "booking_node",
        },
    )

    # Booking → memory save
    builder.add_conditional_edges(
        "booking_node",
        route_after_booking,
        {"memory_save": "memory_save"},
    )

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
    Return the compiled graph singleton.  Creates it on first call.
    Uses PostgreSQL checkpointer when DATABASE_URL is configured,
    falls back to in-memory MemorySaver for local development.
    """
    global _graph_instance
    if _graph_instance is not None:
        return _graph_instance

    checkpointer = await _get_checkpointer()
    _graph_instance = _build_graph(checkpointer)
    logger.info("LangGraph compiled successfully (checkpointer=%s)", type(checkpointer).__name__)
    return _graph_instance


async def _get_checkpointer() -> Any:
    """Return AsyncPostgresSaver if DATABASE_URL is set, else MemorySaver."""
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        logger.warning("DATABASE_URL not set — using in-memory MemorySaver (not for production)")
        return MemorySaver()

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        import psycopg

        # AsyncPostgresSaver requires psycopg3 with autocommit + dict_row
        conn = await psycopg.AsyncConnection.connect(
            database_url,
            autocommit=True,
        )
        checkpointer = AsyncPostgresSaver(conn)
        await checkpointer.setup()  # Creates checkpoint tables if not exist
        logger.info("AsyncPostgresSaver initialized with PostgreSQL")
        return checkpointer
    except Exception as exc:
        logger.error(
            "Failed to initialize AsyncPostgresSaver (%s) — falling back to MemorySaver", exc
        )
        return MemorySaver()


async def reset_graph() -> None:
    """Force recreation of the graph singleton (useful in tests)."""
    global _graph_instance
    _graph_instance = None


# ---------------------------------------------------------------------------
# Synchronous graph for CLI / testing convenience
# ---------------------------------------------------------------------------

def get_graph_sync() -> Any:
    """
    Build a graph with MemorySaver for synchronous use (CLI, pytest).
    """
    return _build_graph(MemorySaver())
