"""HTTP API + static web UI for the planner."""

from __future__ import annotations

import json
import logging
import secrets
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from trip_planner import store
from trip_planner.agent import service
from trip_planner.agent.graph import close_graph
from trip_planner.config import get_settings
from trip_planner.trip import check
from trip_planner.trip.models import Trip

log = logging.getLogger(__name__)
# Built Next.js UI (`cd web && npm run build`); see web/README.md.
WEB = Path(__file__).resolve().parents[2] / "web" / "out"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await store.init_db()
    try:
        yield
    finally:
        await close_graph()
        await store.close_db()


app = FastAPI(title="Trip Planner", lifespan=lifespan)


# ── Auth + rate limit ───────────────────────────────────────────────────────

def _bearer(request: Request) -> str:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    return token if scheme.lower() == "bearer" else ""


def current_user(request: Request) -> str:
    """Checks the API key (if one is configured) and returns the user id."""
    key = get_settings().app_api_key
    if key and not secrets.compare_digest(_bearer(request), key):
        raise HTTPException(401, "missing or wrong API key")
    return "local"  # single-user for now


# ponytail: in-memory per-process limiter; use Redis or a gateway when running multiple workers
_hits: dict[str, deque[float]] = defaultdict(deque)


def rate_limit(request: Request, _user: str = Depends(current_user)) -> None:
    client = _bearer(request) or (request.client.host if request.client else "?")
    now, window = time.monotonic(), _hits[client]
    while window and window[0] <= now - 60:
        window.popleft()
    if len(window) >= get_settings().rate_limit_per_minute:
        raise HTTPException(429, "rate limit exceeded, try again in a minute")
    window.append(now)


# ── Helpers ─────────────────────────────────────────────────────────────────

def annotate(trip: dict) -> dict:
    """Issues and cost for a trip dict, computed by the deterministic checks."""
    t = Trip.model_validate(trip)
    return {
        "issues": [i.model_dump(mode="json") for i in check.check_trip(t)],
        "cost": check.cost_breakdown(t),
    }


def sse(events: AsyncIterator[dict]) -> StreamingResponse:
    async def body():
        try:
            async for event in events:
                if event.get("type") == "trip":
                    event = {**event, **annotate(event["trip"])}
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception as e:
            log.exception("stream failed")
            error = {"type": "error", "message": str(e) or type(e).__name__}
            yield f"data: {json.dumps(error)}\n\n"

    return StreamingResponse(
        body(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


# ── Routes ──────────────────────────────────────────────────────────────────

class MessageIn(BaseModel):
    text: str


class ApprovalIn(BaseModel):
    approved: bool
    note: str = ""


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/trips")
async def create_trip(user: str = Depends(current_user)):
    return {"id": await service.new_trip(user)}


@app.get("/trips")
async def list_trips(user: str = Depends(current_user)):
    rows = await store.list_trips(user)
    keys = ("id", "title", "status", "updated_at")
    return [{k: r[k] for k in keys} | _card(r["trip"] or {}) for r in rows]


def _card(trip: dict) -> dict:
    """What a trip card needs beyond the row: where, when, how long."""
    return {
        "destination": next(iter(trip.get("destinations") or []), ""),
        "start_date": trip.get("start_date"),
        "end_date": trip.get("end_date"),
        "days": len(trip.get("days") or []),
    }


@app.get("/trips/{trip_id}")
async def get_trip(trip_id: str, _user: str = Depends(current_user)):
    thread = await service.get_thread(trip_id)
    if thread is None:
        raise HTTPException(404, "trip not found")
    return {**thread, **annotate(thread["trip"])}


@app.delete("/trips/{trip_id}", status_code=204)
async def delete_trip(trip_id: str, _user: str = Depends(current_user)):
    if not await store.delete_trip(trip_id):
        raise HTTPException(404, "trip not found")
    return Response(status_code=204)


@app.post("/trips/{trip_id}/messages", dependencies=[Depends(rate_limit)])
async def post_message(trip_id: str, body: MessageIn, user: str = Depends(current_user)):
    return sse(service.run_turn(trip_id, body.text, user))


@app.post("/trips/{trip_id}/approval", dependencies=[Depends(rate_limit)])
async def post_approval(trip_id: str, body: ApprovalIn, _user: str = Depends(current_user)):
    return sse(service.resume(trip_id, body.approved, body.note))


# Mounted last so the API routes above take precedence.
if WEB.is_dir():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
else:
    @app.get("/", include_in_schema=False)
    async def index():
        hint = "Web UI not built. Run: cd web && npm install && npm run build"
        return PlainTextResponse(hint, status_code=503)
