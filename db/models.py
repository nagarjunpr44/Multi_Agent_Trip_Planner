from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    user_query: Mapped[str] = mapped_column(Text)
    constraints: Mapped[dict] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    mode: Mapped[str] = mapped_column(String(16), default="autonomous")
    itinerary: Mapped[dict] = mapped_column(JSON, nullable=True)
    booking: Mapped[dict] = mapped_column(JSON, nullable=True)
    raw_state: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    itinerary_records: Mapped[list["ItineraryRecord"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan"
    )
    booking_records: Mapped[list["BookingRecord"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan"
    )


class ItineraryRecord(Base):
    __tablename__ = "itinerary_records"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id"), index=True)
    destination: Mapped[str] = mapped_column(String(256))
    num_days: Mapped[int] = mapped_column(Integer)
    itinerary_json: Mapped[dict] = mapped_column(JSON)
    validation_score: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    trip: Mapped["Trip"] = relationship(back_populates="itinerary_records")


class BookingRecord(Base):
    __tablename__ = "booking_records"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id"), index=True)
    booking_type: Mapped[str] = mapped_column(String(32))  # flight | hotel | activity
    booking_ref: Mapped[str] = mapped_column(String(128))
    provider: Mapped[str] = mapped_column(String(64))
    amount_usd: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    details_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    trip: Mapped["Trip"] = relationship(back_populates="booking_records")


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    preference_key: Mapped[str] = mapped_column(String(128))
    preference_value: Mapped[str] = mapped_column(Text)
    embedding_id: Mapped[str] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
