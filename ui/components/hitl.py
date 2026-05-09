"""HITL (Human-in-the-Loop) approval widget."""
from __future__ import annotations

import requests
import streamlit as st


def render_hitl(api_url: str, session_id: str) -> None:
    """
    Render the HITL approval/rejection widget.
    Called when the graph pauses before booking.
    """
    st.divider()
    st.subheader("👤 Human Approval Required")
    st.info(
        "The AI has completed research, flights, hotels, experiences, budget, "
        "and itinerary planning. Please review and approve or reject the plan below."
    )

    # Fetch current trip state to show summary
    try:
        resp = requests.get(f"{api_url}/trips/{session_id}", timeout=10)
        resp.raise_for_status()
        trip = resp.json()
        itinerary = trip.get("itinerary") or {}
        raw_state = trip.get("raw_state") or {}
        validation = raw_state.get("validation_result") or {}
        budget = raw_state.get("budget_analysis") or {}
    except Exception:
        itinerary = {}
        validation = {}
        budget = {}

    # Show validation score
    score = validation.get("score", 0)
    issues = validation.get("issues", [])
    suggestions = validation.get("suggestions", [])

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Validation Score", f"{score:.0%}")
        if issues:
            st.markdown("**Issues:**")
            for issue in issues:
                st.markdown(f"- ⚠️ {issue}")
    with col2:
        mid = (budget.get("mid") or {})
        st.metric("Estimated Cost", f"${mid.get('total_usd', 'N/A')}")
        if suggestions:
            st.markdown("**Suggestions:**")
            for s in suggestions[:3]:
                st.markdown(f"- 💡 {s}")

    # Itinerary quick view
    if itinerary.get("days"):
        st.markdown("**Itinerary Preview:**")
        for day in itinerary["days"][:3]:
            st.markdown(
                f"**Day {day.get('day_number')}: {day.get('theme')}**"
                f" — {', '.join(a.get('name','') for a in day.get('activities', [])[:2])}"
            )

    st.divider()
    feedback = st.text_area(
        "Feedback / modifications (optional)",
        placeholder="e.g. 'Upgrade hotel to 5-star', 'Add more beach activities'",
    )

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("✅ Approve & Book", type="primary", use_container_width=True):
            _submit_decision(api_url, session_id, approved=True, feedback=feedback)
    with col_b:
        if st.button("❌ Reject", use_container_width=True):
            _submit_decision(api_url, session_id, approved=False, feedback=feedback)


def _submit_decision(api_url: str, session_id: str, approved: bool, feedback: str) -> None:
    endpoint = "approve" if approved else "reject"
    try:
        resp = requests.post(
            f"{api_url}/trips/{session_id}/{endpoint}",
            json={"approved": approved, "feedback": feedback or None},
            timeout=10,
        )
        resp.raise_for_status()
        if approved:
            st.success("✅ Approved! Booking in progress...")
        else:
            st.warning("❌ Trip rejected.")
    except Exception as exc:
        st.error(f"Failed to submit decision: {exc}")
