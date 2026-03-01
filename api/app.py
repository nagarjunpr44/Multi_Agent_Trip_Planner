from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware import RequestIDMiddleware
from api.routes import health, hitl, planning, streaming, trips, websocket
from cache.redis_client import close_redis_client, init_redis_client
from db.connection import create_tables, dispose_engine
from tools.registry import initialize_registry

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup → yield → shutdown."""
    logger.info("Starting AgenticTripPlanner API...")

    # Database (SQLite or Postgres)
    try:
        await create_tables()
    except Exception as exc:
        logger.warning("create_tables failed (non-fatal): %s", exc)

    # Redis (optional — gracefully skipped if unavailable)
    await init_redis_client()

    # Tool registry
    initialize_registry()

    # Pre-warm the graph (compiles StateGraph, connects checkpointer)
    try:
        from agents.graph import get_graph
        await get_graph()
    except Exception as exc:
        logger.warning("Graph pre-warm failed (will retry on first request): %s", exc)

    logger.info("AgenticTripPlanner API ready.")
    yield

    # Shutdown
    await dispose_engine()
    await close_redis_client()
    logger.info("AgenticTripPlanner API shut down.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="AgenticTripPlanner",
        version="1.0.0",
        description=(
            "Production-grade AI travel planning system using LangGraph multi-agent orchestration."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── Middleware ─────────────────────────────────────────────────────────
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes ─────────────────────────────────────────────────────────────
    app.include_router(health.router)
    app.include_router(planning.router)
    app.include_router(trips.router)
    app.include_router(streaming.router)
    app.include_router(hitl.router)
    app.include_router(websocket.router)

    return app
