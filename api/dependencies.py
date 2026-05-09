from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agents.graph import get_graph
from cache.redis_client import StreamEventPublisher
from db.connection import get_db_session

_publisher_instance = StreamEventPublisher()


# ── Database session ───────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_db_session() as session:
        yield session


DBSession = Annotated[AsyncSession, Depends(get_db)]


# ── Redis publisher ────────────────────────────────────────────────────────

async def get_publisher() -> StreamEventPublisher:
    return _publisher_instance


Publisher = Annotated[StreamEventPublisher, Depends(get_publisher)]


# ── LangGraph instance ─────────────────────────────────────────────────────

async def get_compiled_graph():
    return await get_graph()


Graph = Annotated[object, Depends(get_compiled_graph)]
