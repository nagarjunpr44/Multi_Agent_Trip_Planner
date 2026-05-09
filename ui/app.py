"""
AgenticTripPlanner — Streamlit UI
Entry point: `streamlit run ui/app.py`
"""
from __future__ import annotations

import os
import sys

# Ensure project root is on path when running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

st.set_page_config(
    page_title="AgenticTripPlanner",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar navigation ─────────────────────────────────────────────────────

st.sidebar.title("✈️ AgenticTripPlanner")
st.sidebar.markdown("*Chat with your AI travel agent*")
st.sidebar.divider()

page = st.sidebar.radio(
    "Navigate",
    ["Chat & Plan", "My Trips"],
    index=0,
)

st.sidebar.divider()
api_url = st.sidebar.text_input(
    "API URL",
    value=os.getenv("FASTAPI_BASE_URL", os.getenv("API_URL", "http://localhost:8000")),
    help="AgenticTripPlanner FastAPI backend URL",
)
# Persist across pages via session state
st.session_state["api_url"] = api_url

# ── Page routing ───────────────────────────────────────────────────────────

if page == "Chat & Plan":
    from ui.pages.plan_trip import render
    render()
elif page == "My Trips":
    from ui.pages.my_trips import render
    render()
