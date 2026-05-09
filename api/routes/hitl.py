from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException

from agents.graph import get_graph
from api.dependencies import DBSession, Publisher
from db.connection import get_db_session
from db.repository import TripRepository
from schemas.trip import HITLResumeRequest

router = APIRouter(prefix="/trips", tags=["hitl"])
logger = logging.getLogger(__name__)


@router.post("/{session_id}/approve")
async def approve_trip(
    session_id: str,
    body: HITLResumeRequest,
    background_tasks: BackgroundTasks,
    db: DBSession,
    publisher: Publisher,
) -> dict:
    """
    Resume a paused HITL graph run with user approval.
    Optionally accepts feedback that is injected into the state before booking.
    """
    repo = TripRepository(db)
    trip = await repo.get_trip(session_id)
    if not trip:
        raise HTTPException(status_code=404, detail=f"Trip {session_id} not found")

    background_tasks.add_task(
        _resume_graph,
        session_id=session_id,
        human_approved=True,
        human_feedback=body.feedback,
        publisher=publisher,
    )

    return {"session_id": session_id, "status": "resuming", "approved": True}


@router.post("/{session_id}/reject")
async def reject_trip(
    session_id: str,
    body: HITLResumeRequest,
    db: DBSession,
    publisher: Publisher,
) -> dict:
    """
    Reject the current plan — the graph is NOT resumed.
    Publishes an error event so clients know the run is cancelled.
    """
    repo = TripRepository(db)
    trip = await repo.get_trip(session_id)
    if not trip:
        raise HTTPException(status_code=404, detail=f"Trip {session_id} not found")

    await publisher.publish(
        session_id,
        "error",
        {
            "message": "Trip planning rejected by user.",
            "reason": body.feedback or "No reason provided.",
        },
    )
    await repo.update_status(session_id, "rejected")

    return {"session_id": session_id, "status": "rejected"}


async def _resume_graph(
    session_id: str,
    human_approved: bool,
    human_feedback: str | None,
    publisher: Publisher,
) -> None:
    """Resume the graph after HITL interrupt."""
    try:
        graph = await get_graph()
        config = {"configurable": {"thread_id": session_id}}

        # Update state with approval and feedback
        update = {"human_approved": human_approved}
        if human_feedback:
            update["human_feedback"] = human_feedback

        await graph.aupdate_state(config, update)

        # Resume by streaming with None input (continues from interrupt)
        async for event in graph.astream_events(None, config=config, version="v2"):  # type: ignore[arg-type]
            event_type = event.get("event", "")
            node_name = (event.get("metadata") or {}).get("langgraph_node", "")
            if event_type == "on_chain_start" and node_name:
                await publisher.publish(session_id, "agent_start", {"node": node_name})
            elif event_type == "on_chain_end" and node_name:
                await publisher.publish(session_id, "agent_complete", {"node": node_name})

        final_state = await graph.aget_state(config)
        raw_state = final_state.values if final_state else {}
        async with get_db_session() as db:
            repo = TripRepository(db)
            await repo.update_raw_state(session_id, raw_state)
            await repo.update_status(session_id, "complete")

        await publisher.publish(session_id, "graph_complete", {"session_id": session_id})

    except Exception as exc:
        logger.exception("Graph resume failed for session %s: %s", session_id, exc)
        await publisher.publish(session_id, "error", {"message": str(exc)})
