from __future__ import annotations

import json
from typing import Any, Optional

import redis.asyncio as aioredis

from config.settings import get_settings

_redis_client: Optional[aioredis.Redis] = None
_redis_available: bool = False


async def init_redis_client() -> None:
    """Connect to Redis at startup. Logs a warning and continues if unavailable."""
    global _redis_client, _redis_available
    try:
        settings = get_settings()
        client = aioredis.from_url(
            settings.redis.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        await client.ping()
        _redis_client = client
        _redis_available = True
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "Redis unavailable (%s) — SSE streaming disabled, API still functional.", exc
        )
        _redis_available = False


async def close_redis_client() -> None:
    global _redis_client, _redis_available
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
    _redis_available = False


def get_redis() -> Optional[aioredis.Redis]:
    return _redis_client if _redis_available else None


# Alias used by api/dependencies.py
get_redis_client = get_redis


async def close_redis() -> None:
    await close_redis_client()


class StreamEventPublisher:
    """Publishes agent progress events to a Redis Stream for SSE/WS consumers."""

    STREAM_PREFIX = "trip:events:"

    def __init__(self) -> None:
        self._ttl = get_settings().redis.redis_stream_ttl_seconds

    def _stream_key(self, session_id: str) -> str:
        return f"{self.STREAM_PREFIX}{session_id}"

    async def publish(self, session_id: str, event_type: str, data: Any) -> None:
        r = get_redis()
        if r is None:
            return  # Redis unavailable — silently skip
        try:
            payload = json.dumps({"type": event_type, "data": data})
            stream_key = self._stream_key(session_id)
            await r.xadd(stream_key, {"payload": payload}, maxlen=500, approximate=True)
            await r.expire(stream_key, self._ttl)
        except Exception:
            pass  # Non-fatal

    async def publish_agent_start(self, session_id: str, agent_name: str) -> None:
        await self.publish(session_id, "agent_start", {"agent": agent_name})

    async def publish_agent_complete(self, session_id: str, agent_name: str, summary: str = "") -> None:
        await self.publish(session_id, "agent_complete", {"agent": agent_name, "summary": summary})

    async def publish_graph_complete(self, session_id: str) -> None:
        await self.publish(session_id, "graph_complete", {"session_id": session_id})

    async def publish_error(self, agent_name: str, error: str) -> None:
        await self.publish("error", {"agent": agent_name, "error": error})

    async def publish_hitl_pause(self) -> None:
        await self.publish("hitl_pause", {"message": "Awaiting your approval to proceed with booking."})

    async def read_events(self, last_id: str = "0") -> list[dict]:
        """Read events from the stream starting after last_id."""
        entries = await self._redis.xread({self._stream_key: last_id}, count=50, block=500)
        events = []
        for _stream, messages in entries:
            for msg_id, fields in messages:
                events.append({"id": msg_id, **json.loads(fields["payload"])})
        return events
