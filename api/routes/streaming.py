from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from api.dependencies import DBSession
from cache.redis_client import get_redis_client

router = APIRouter(prefix="/trips", tags=["streaming"])
logger = logging.getLogger(__name__)

_TERMINAL_EVENTS = {"graph_complete", "error"}


@router.get("/{session_id}/stream", response_class=StreamingResponse)
async def stream_trip_events(session_id: str, db: DBSession) -> StreamingResponse:
    """
    SSE endpoint — streams Redis Stream events for the given session_id.
    Clients connect here and receive real-time agent progress events.
    Response format: text/event-stream (SSE).
    """
    return StreamingResponse(
        _sse_generator(session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _sse_generator(session_id: str) -> AsyncGenerator[str, None]:
    redis = get_redis_client()
    if redis is None:
        yield f"data: {json.dumps({'event': 'error', 'message': 'Redis unavailable'})}\n\n"
        return

    stream_key = f"trip:events:{session_id}"
    last_id = "0"

    # Yield initial connection confirmation
    yield f"data: {json.dumps({'event': 'connected', 'session_id': session_id})}\n\n"

    while True:
        try:
            messages = await redis.xread({stream_key: last_id}, block=5000, count=10)
        except Exception as exc:
            logger.warning("Redis xread error for %s: %s", session_id, exc)
            yield f"data: {json.dumps({'event': 'error', 'message': str(exc)})}\n\n"
            break

        if messages:
            for _, entries in messages:
                for entry_id, fields in entries:
                    last_id = entry_id
                    payload_raw = fields.get("payload", "{}")
                    try:
                        payload = json.loads(payload_raw)
                    except json.JSONDecodeError:
                        payload = {"type": "unknown", "data": {}}

                    event_type = payload.get("type", "message")
                    event_data = payload.get("data", {})
                    sse_chunk = json.dumps({"event": event_type, **event_data})
                    yield f"data: {sse_chunk}\n\n"

                    if event_type in _TERMINAL_EVENTS:
                        return
        else:
            # Keep-alive ping every 5 s
            yield ": keep-alive\n\n"
