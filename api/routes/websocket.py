from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from cache.redis_client import get_redis_client

router = APIRouter(tags=["websocket"])
logger = logging.getLogger(__name__)

_TERMINAL_EVENTS = {"graph_complete", "error"}


@router.websocket("/ws/trips/{session_id}")
async def websocket_trip_events(websocket: WebSocket, session_id: str) -> None:
    """
    WebSocket endpoint — streams the same Redis Stream events as the SSE endpoint.
    Clients can also send messages to be echoed back (ping/pong keepalive).
    """
    await websocket.accept()
    redis = await get_redis_client()
    stream_key = f"trip:events:{session_id}"
    last_id = "0"

    await websocket.send_json({"event": "connected", "session_id": session_id})

    try:
        while True:
            try:
                messages = await redis.xread({stream_key: last_id}, block=5000, count=10)
            except Exception as exc:
                logger.warning("Redis xread error for WS %s: %s", session_id, exc)
                await websocket.send_json({"event": "error", "message": str(exc)})
                break

            if messages:
                for _, entries in messages:
                    for entry_id, fields in entries:
                        last_id = entry_id
                        event_type = fields.get("event", "message")
                        payload_raw = fields.get("data", "{}")
                        try:
                            payload = json.loads(payload_raw)
                        except json.JSONDecodeError:
                            payload = {"raw": payload_raw}

                        await websocket.send_json({"event": event_type, **payload})

                        if event_type in _TERMINAL_EVENTS:
                            await websocket.close()
                            return
            else:
                # Keep-alive ping
                await websocket.send_json({"event": "ping"})

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected for session %s", session_id)
