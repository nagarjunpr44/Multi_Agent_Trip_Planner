from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BookingRecord, ItineraryRecord, Trip


def _json_safe(obj: object) -> object:
    """Recursively convert a nested dict/list so it's JSON-serialisable."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, set):
        return list(obj)
    # Let anything json.dumps already handles pass through
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)


class TripRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_trip(
        self,
        user_query: str,
        mode: str = "autonomous",
        session_id: Optional[str] = None,
        constraints: Optional[dict] = None,
    ) -> Trip:
        session_id = session_id or str(uuid.uuid4())
        trip = Trip(
            session_id=session_id,
            user_query=user_query,
            constraints=constraints,
            status="queued",
            mode=mode,
        )
        self._session.add(trip)
        await self._session.flush()
        return trip

    async def get_by_session_id(self, session_id: str) -> Optional[Trip]:
        result = await self._session.execute(
            select(Trip).where(Trip.session_id == session_id)
        )
        return result.scalar_one_or_none()

    # Alias used by api/routes/trips.py
    get_trip = get_by_session_id

    async def get_by_id(self, trip_id: str) -> Optional[Trip]:
        result = await self._session.execute(
            select(Trip).where(Trip.id == trip_id)
        )
        return result.scalar_one_or_none()

    async def list_trips(self, limit: int = 20, offset: int = 0) -> list[Trip]:
        result = await self._session.execute(
            select(Trip).order_by(Trip.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def update_status(self, session_id: str, status: str) -> None:
        trip = await self.get_by_session_id(session_id)
        if trip:
            trip.status = status
            trip.updated_at = datetime.now(timezone.utc)
            await self._session.flush()

    async def update_raw_state(self, session_id: str, raw_state: dict) -> None:
        trip = await self.get_by_session_id(session_id)
        if trip:
            safe = _json_safe(raw_state)
            trip.raw_state = safe
            trip.itinerary = _json_safe(raw_state.get("itinerary"))
            trip.booking = _json_safe(raw_state.get("booking_result"))
            trip.updated_at = datetime.now(timezone.utc)
            await self._session.flush()

    async def delete_trip(self, session_id: str) -> bool:
        trip = await self.get_by_session_id(session_id)
        if trip:
            await self._session.delete(trip)
            await self._session.flush()
            return True
        return False

    async def save_itinerary(
        self,
        trip_id: str,
        destination: str,
        num_days: int,
        itinerary_json: dict,
        validation_score: Optional[float] = None,
    ) -> ItineraryRecord:
        record = ItineraryRecord(
            trip_id=trip_id,
            destination=destination,
            num_days=num_days,
            itinerary_json=itinerary_json,
            validation_score=validation_score,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def save_booking(
        self,
        trip_id: str,
        booking_type: str,
        booking_ref: str,
        provider: str,
        amount_usd: float,
        status: str = "pending",
        details_json: Optional[dict] = None,
    ) -> BookingRecord:
        record = BookingRecord(
            trip_id=trip_id,
            booking_type=booking_type,
            booking_ref=booking_ref,
            provider=provider,
            amount_usd=amount_usd,
            status=status,
            details_json=details_json or {},
        )
        self._session.add(record)
        await self._session.flush()
        return record
