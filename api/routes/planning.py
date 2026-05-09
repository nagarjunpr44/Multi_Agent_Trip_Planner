from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks

from agents.graph import get_graph
from api.dependencies import DBSession, Publisher
from db.connection import get_db_session
from db.repository import TripRepository
from schemas.trip import TripRequest, TripResponse, TripStatus

router = APIRouter(prefix="/trips", tags=["planning"])
logger = logging.getLogger(__name__)


@router.post("", response_model=TripResponse, status_code=202)
async def start_planning(
    request: TripRequest,
    background_tasks: BackgroundTasks,
    db: DBSession,
    publisher: Publisher,
) -> TripResponse:
    """
    Start an async trip planning run.
    Returns immediately with a session_id; the graph runs in the background.
    Poll GET /trips/{session_id} or stream events via SSE/WS.
    """
    session_id = str(uuid.uuid4())

    repo = TripRepository(db)
    await repo.create_trip(
        session_id=session_id,
        user_query=request.user_query,
        constraints=request.constraints.model_dump(mode="json") if request.constraints else {},
    )

    background_tasks.add_task(
        _run_graph,
        session_id=session_id,
        request=request,
        publisher=publisher,
    )

    return TripResponse(
        session_id=session_id,
        status=TripStatus.PENDING,
        message="Trip planning started. Connect to /trips/{session_id}/stream for live updates.",
    )


async def _run_graph(
    session_id: str,
    request: TripRequest,
    publisher: Publisher,
) -> None:
    """Background task: invoke the LangGraph graph and stream events via Redis."""
    try:
        graph = await get_graph()

        constraints = request.constraints.model_dump(mode="json") if request.constraints else {}
        initial_state = {
            "session_id": session_id,
            "user_query": request.user_query,
            "constraints": constraints,
            "mode": request.mode or "autonomous",
            "messages": [],
            "revision_count": 0,
            "status": "running",
            "errors": [],
            "agent_timings": {},
        }

        config = {"configurable": {"thread_id": session_id}}

        await publisher.publish(session_id, "graph_start", {"session_id": session_id})

        started_nodes: set[str] = set()
        completed_nodes: set[str] = set()

        async for event in graph.astream_events(initial_state, config=config, version="v2"):
            event_type = event.get("event", "")
            node_name = (event.get("metadata") or {}).get("langgraph_node", "")

            if event_type == "on_chain_start" and node_name and node_name not in started_nodes:
                started_nodes.add(node_name)
                await publisher.publish(session_id, "agent_start", {"node": node_name})

            elif event_type == "on_chain_end" and node_name and node_name not in completed_nodes:
                completed_nodes.add(node_name)
                output = event.get("data", {}).get("output", {})
                output_keys = list(output.keys()) if isinstance(output, dict) else []
                await publisher.publish(
                    session_id,
                    "agent_complete",
                    {"node": node_name, "output_keys": output_keys},
                )

        # Grab the final state snapshot from the graph
        final_state = await graph.aget_state(config)
        raw_state = final_state.values if final_state else {}

        # Persist final state to DB (background task has no request-scoped session)
        async with get_db_session() as db:
            repo = TripRepository(db)
            await repo.update_raw_state(session_id, raw_state)
            await repo.update_status(session_id, "complete")

        # Signal SSE consumers to close
        await publisher.publish(session_id, "graph_complete", {"session_id": session_id})

    except Exception as exc:
        logger.exception("Graph run failed for session %s: %s", session_id, exc)
        await publisher.publish(session_id, "error", {"message": str(exc)})
        try:
            async with get_db_session() as db:
                repo = TripRepository(db)
                await repo.update_status(session_id, "failed")
        except Exception:
            logger.exception("Failed to update trip status to 'failed'")
