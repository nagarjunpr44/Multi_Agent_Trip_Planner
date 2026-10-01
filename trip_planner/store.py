"""App tables: trips index, user preferences, tool response cache.

Conversation + trip state live in the LangGraph checkpointer; the `trips`
table is just an index (title/status/latest snapshot) for listing.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import JSON, DateTime, String, Text, delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from trip_planner.config import get_settings


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TripRow(Base):
    __tablename__ = "trips"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), default="local", index=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    status: Mapped[str] = mapped_column(String(32), default="planning")
    trip: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PreferenceRow(Base):
    __tablename__ = "preferences"
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class CacheRow(Base):
    __tablename__ = "tool_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


_engine: AsyncEngine | None = None
_sessions: async_sessionmaker | None = None


async def init_db(url: str | None = None) -> None:
    global _engine, _sessions
    url = url or get_settings().app_db_url
    if url.startswith("sqlite") and ":///" in url:
        path = url.split(":///", 1)[1]
        if path and path != ":memory:":
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    _engine = create_async_engine(url)
    _sessions = async_sessionmaker(_engine, expire_on_commit=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    global _engine, _sessions
    if _engine is not None:
        await _engine.dispose()
    _engine = _sessions = None


def _session():
    if _sessions is None:
        raise RuntimeError("store.init_db() has not been called")
    return _sessions()


# ── Trips index ────────────────────────────────────────────────────────────

async def upsert_trip(trip: dict, user_id: str = "local") -> None:
    async with _session() as s, s.begin():
        row = await s.get(TripRow, trip["id"])
        if row is None:
            row = TripRow(id=trip["id"], user_id=user_id)
            s.add(row)
        row.title = trip.get("title", "")
        row.status = trip.get("status", "planning")
        row.trip = trip
        row.updated_at = _now()


async def get_trip(trip_id: str) -> dict | None:
    async with _session() as s:
        row = await s.get(TripRow, trip_id)
        return None if row is None else _trip_row(row)


async def list_trips(user_id: str = "local", limit: int = 50) -> list[dict]:
    async with _session() as s:
        rows = await s.scalars(
            select(TripRow)
            .where(TripRow.user_id == user_id)
            .order_by(TripRow.updated_at.desc())
            .limit(limit)
        )
        return [_trip_row(r) for r in rows]


async def delete_trip(trip_id: str) -> bool:
    async with _session() as s, s.begin():
        result = await s.execute(delete(TripRow).where(TripRow.id == trip_id))
        return result.rowcount > 0


def _trip_row(r: TripRow) -> dict:
    return {
        "id": r.id,
        "title": r.title,
        "status": r.status,
        "trip": r.trip,
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
    }


# ── Preferences (explicit facts the user told us, e.g. diet=vegetarian) ─────

async def set_preference(key: str, value: str, user_id: str = "local") -> None:
    async with _session() as s, s.begin():
        row = await s.get(PreferenceRow, (user_id, key))
        if row is None:
            s.add(PreferenceRow(user_id=user_id, key=key, value=value))
        else:
            row.value, row.updated_at = value, _now()


async def get_preferences(user_id: str = "local") -> dict[str, str]:
    async with _session() as s:
        rows = await s.scalars(select(PreferenceRow).where(PreferenceRow.user_id == user_id))
        return {r.key: r.value for r in rows}


# ── Tool response cache ─────────────────────────────────────────────────────

async def cache_get(key: str) -> Any | None:
    if _sessions is None:  # cache is optional: tools work without a DB
        return None
    async with _session() as s:
        row = await s.get(CacheRow, key)
        if row is None or row.expires_at.replace(tzinfo=UTC) < _now():
            return None
        return json.loads(row.value)


async def cache_set(key: str, value: Any, ttl_hours: float | None = None) -> None:
    if _sessions is None:
        return
    ttl = ttl_hours if ttl_hours is not None else get_settings().cache_ttl_hours
    async with _session() as s, s.begin():
        await s.merge(
            CacheRow(key=key, value=json.dumps(value), expires_at=_now() + timedelta(hours=ttl))
        )
