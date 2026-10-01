"""Deterministic trip checks. No LLM, no network."""

from __future__ import annotations

from trip_planner.trip.models import Issue, Trip


def check_trip(trip: Trip) -> list[Issue]:
    """Every concrete problem with the trip, errors first."""
    raise NotImplementedError


def cost_breakdown(trip: Trip) -> dict:
    """{"flight", "hotel", "activities", "total", "budget" (or None), "remaining" (or None)}"""
    raise NotImplementedError
