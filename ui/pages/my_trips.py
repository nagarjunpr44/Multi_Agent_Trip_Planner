"""My Trips — browse and manage past planning sessions."""
from __future__ import annotations

import os

import requests
import streamlit as st


def render() -> None:
    st.title("📂 My Trips")

    api_url = st.session_state.get("api_url", "http://localhost:8000")

    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button("🔄 Refresh"):
            st.rerun()

    try:
        resp = requests.get(f"{api_url}/trips", params={"limit": 50}, timeout=10)
        resp.raise_for_status()
        trips = resp.json()
    except Exception as exc:
        st.error(f"Could not load trips: {exc}")
        return

    if not trips:
        st.info("No trips found. Go to **Plan a Trip** to get started!")
        return

    for trip in trips:
        session_id = trip.get("session_id", "")
        status = trip.get("status", "unknown")
        query = trip.get("user_query", "")
        created = trip.get("created_at", "")

        status_emoji = {
            "complete": "✅",
            "completed": "✅",
            "failed": "❌",
            "queued": "🕒",
            "running": "⏳",
            "pending": "🕒",
            "rejected": "❌",
            "paused_hitl": "👤",
        }.get(status, "❓")

        with st.expander(f"{status_emoji} {query[:80]}... — {created[:10] if created else 'N/A'}"):
            st.markdown(f"**Session ID:** `{session_id}`")
            st.markdown(f"**Status:** {status}")

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("View Details", key=f"view_{session_id}"):
                    _show_trip_detail(api_url, session_id)
            with col_b:
                if st.button("🗑️ Delete", key=f"del_{session_id}"):
                    try:
                        requests.delete(f"{api_url}/trips/{session_id}", timeout=10)
                        st.success("Deleted.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Delete failed: {exc}")


def _show_trip_detail(api_url: str, session_id: str) -> None:
    try:
        resp = requests.get(f"{api_url}/trips/{session_id}", timeout=10)
        resp.raise_for_status()
        trip = resp.json()
    except Exception as exc:
        st.error(f"Could not load trip: {exc}")
        return

    itinerary = trip.get("itinerary") or {}
    booking = trip.get("booking") or {}

    st.divider()
    if itinerary:
        st.subheader(f"🗺️ Itinerary: {itinerary.get('destination', 'N/A')}")
        for day in itinerary.get("days", []):
            theme = day.get("theme") or "Exploration"
            st.markdown(
                f"**Day {day.get('day_number')}: {theme}** ({day.get('date', '')})"
            )
            all_acts = (
                (day.get("morning") or [])
                + (day.get("afternoon") or [])
                + (day.get("evening") or [])
            ) or day.get("activities", [])
            for act in all_acts[:5]:
                cost = f" *${act.get('cost_usd')}*" if act.get("cost_usd") else ""
                st.markdown(f"  - {act.get('name', '')}{cost}")

    if booking:
        st.subheader("🎫 Booking")
        st.json(booking)


if __name__ == "__main__":
    st.session_state.setdefault(
        "api_url",
        os.getenv("FASTAPI_BASE_URL", os.getenv("API_URL", "http://localhost:8000")),
    )
    render()
