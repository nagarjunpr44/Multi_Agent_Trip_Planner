from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.dependencies import DBSession
from db.repository import TripRepository
from schemas.trip import TripResponse

router = APIRouter(prefix="/trips", tags=["trips"])


@router.get("", response_model=list[TripResponse])
async def list_trips(db: DBSession, limit: int = 20, offset: int = 0) -> list[TripResponse]:
    repo = TripRepository(db)
    trips = await repo.list_trips(limit=limit, offset=offset)
    return [
        TripResponse(
            session_id=t.session_id,
            status=t.status,
            user_query=t.user_query,
            created_at=t.created_at.isoformat() if t.created_at else None,
        )
        for t in trips
    ]


@router.get("/{session_id}", response_model=TripResponse)
async def get_trip(session_id: str, db: DBSession) -> TripResponse:
    repo = TripRepository(db)
    trip = await repo.get_trip(session_id)
    if not trip:
        raise HTTPException(status_code=404, detail=f"Trip {session_id} not found")
    return TripResponse(
        session_id=trip.session_id,
        status=trip.status,
        user_query=trip.user_query,
        constraints=trip.constraints,
        itinerary=trip.itinerary,
        booking=trip.booking,
        raw_state=trip.raw_state,
        created_at=trip.created_at.isoformat() if trip.created_at else None,
        updated_at=trip.updated_at.isoformat() if trip.updated_at else None,
    )


@router.delete("/{session_id}", status_code=204)
async def delete_trip(session_id: str, db: DBSession) -> None:
    repo = TripRepository(db)
    deleted = await repo.delete_trip(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Trip {session_id} not found")
