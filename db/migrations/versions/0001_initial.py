"""Initial schema — trips, itineraries, bookings, user_preferences

Revision ID: 0001_initial
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trips",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("user_query", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=True, server_default="pending"),
        sa.Column("constraints", sa.JSON(), nullable=True),
        sa.Column("itinerary", sa.JSON(), nullable=True),
        sa.Column("booking", sa.JSON(), nullable=True),
        sa.Column("raw_state", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index("ix_trips_session_id", "trips", ["session_id"])
    op.create_index("ix_trips_status", "trips", ["status"])

    op.create_table(
        "itinerary_records",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["session_id"], ["trips.session_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "booking_records",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("booking_reference", sa.String(length=32), nullable=True),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["session_id"], ["trips.session_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_preferences_user_id", "user_preferences", ["user_id"])


def downgrade() -> None:
    op.drop_table("user_preferences")
    op.drop_table("booking_records")
    op.drop_table("itinerary_records")
    op.drop_table("trips")
