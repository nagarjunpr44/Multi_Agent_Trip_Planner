"""
Chat-based trip planning page.

The user talks to an AI travel agent who gathers requirements conversationally,
then kicks off the LangGraph planning pipeline when ready.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import date
from typing import Any

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PLAN_TAG_OPEN = "<!--PLAN_JSON"
_PLAN_TAG_CLOSE = "PLAN_JSON-->"

_TODAY = date.today().isoformat()

_SYSTEM_PROMPT = f"""\
You are **TravelBot**, a friendly AI travel-intake agent.
Today's date is {_TODAY}.

YOUR ROLE: You gather trip requirements through brief, warm conversation, \
then HAND OFF to a specialist planning system. You do NOT plan the trip yourself. \
You do NOT suggest itineraries, hotels, or activities. Your ONLY job is to \
collect enough info and then emit the handoff JSON block described below.

Collect these details naturally (2-3 questions max per turn):
  1. Destination(s)
  2. Travel dates or duration
  3. Number of travellers
  4. Budget (rough range is fine)
  5. Interests / activity preferences
  6. Any special needs (dietary, accessibility, etc.)

CRITICAL RULES:
- You MUST ensure you have ALL of these mandatory details before handing off:
  1. DESTINATION
  2. EXACT TRAVEL DATES (e.g., April 10th to April 13th, 2026).
     Just a duration or month is NOT enough.
  3. ORIGIN CITY (where they are flying from). Do NOT default to JFK.
  4. BUDGET
- If the user provides a month or duration without exact dates, ask them explicitly
  for the exact dates (we need them to search flights).
- If the user forgets their origin city, ask them explicitly.
- Once you have ALL the mandatory info, write a short friendly handoff message
  and IMMEDIATELY append the hidden JSON block below.

HANDOFF FORMAT — append this at the VERY END of your message:

{_PLAN_TAG_OPEN}
{{"user_query": "<full natural-language summary of the trip>",
 "constraints": {{
   "destinations": ["..."],
   "departure_date": "YYYY-MM-DD or null",
   "return_date": "YYYY-MM-DD or null",
   "duration_days": <number or null>,
   "num_travelers": 1,
   "budget_usd": <number or null>,
   "budget_tier": "budget" or "mid" or "luxury",
   "activity_preferences": ["..."],
   "origin_city": "<city or null>"
 }}}}
{_PLAN_TAG_CLOSE}

The user will NOT see the JSON block — it is parsed by the system.
If the user gives budget in EUR, convert roughly to USD (1 EUR ≈ 1.08 USD).
NEVER skip the JSON block when you have enough info. ALWAYS include it."""

_GREETING = (
    "Hey there! ✈️ I'm your personal travel agent. "
    "Tell me about the trip you're dreaming of — where do you want to go, "
    "when are you thinking of travelling, and what kind of experience are you after? "
    "I'll take care of the rest!"
)

_NODE_LABELS: dict[str, str] = {
    "supervisor": "🗺️ Supervisor",
    "research_agent": "🔍 Researching destinations",
    "flight_search_agent": "✈️ Searching flights",
    "hotel_search_agent": "🏨 Finding hotels",
    "experience_search_agent": "🎭 Discovering experiences",
    "budget_optimization_agent": "💰 Optimizing budget",
    "itinerary_compilation_agent": "📋 Building itinerary",
    "itinerary_validator_agent": "✅ Validating itinerary",
    "booking_agent": "🎫 Booking",
    "booking_node": "🎫 Booking",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_openai():
    """Return an OpenAI client."""
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        # Try loading from .env file
        env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
        env_path = os.path.abspath(env_path)
        if os.path.exists(env_path):
            for line in open(env_path):
                line = line.strip()
                if line.startswith("OPENAI_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not api_key:
        st.error("OPENAI_API_KEY not found. Set it in your .env file.")
        st.stop()
    return OpenAI(api_key=api_key)


def _extract_plan(text: str) -> dict | None:
    """Extract the hidden PLAN_JSON block from assistant text (if present)."""
    pattern = re.compile(
        re.escape(_PLAN_TAG_OPEN) + r"\s*(.*?)\s*" + re.escape(_PLAN_TAG_CLOSE),
        re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _strip_plan_block(text: str) -> str:
    """Remove the hidden JSON block so the user never sees it."""
    pattern = re.compile(
        re.escape(_PLAN_TAG_OPEN) + r".*?" + re.escape(_PLAN_TAG_CLOSE),
        re.DOTALL,
    )
    return pattern.sub("", text).rstrip()


def _pretty_node(node: str) -> str:
    return _NODE_LABELS.get(node, node.replace("_", " ").title())


def _api_url() -> str:
    return st.session_state.get("api_url", "http://localhost:8000")


def _force_extract_plan(client, history: list[dict]) -> dict | None:
    """
    Fallback: ask the LLM explicitly to emit just the JSON plan
    based on the conversation so far.
    """
    extraction_messages = [
        {"role": "system", "content": (
            "You are a data extraction assistant. Based on the travel conversation "
            "below, produce a JSON object with exactly these keys:\n"
            '{"user_query": "...", "constraints": {"destinations": [...], '
            '"departure_date": "YYYY-MM-DD or null", "return_date": "YYYY-MM-DD or null", '
            '"duration_days": N, "num_travelers": N, "budget_usd": N, '
            '"budget_tier": "budget|mid|luxury", "activity_preferences": [...], '
            '"origin_city": "..."}}\n'
            "Respond with ONLY the JSON object, no other text. "
            "If budget is in EUR, convert to USD (1 EUR ≈ 1.08 USD). "
            "Fill in reasonable defaults for missing fields."
        )},
    ]
    # Include only user/assistant messages (skip system)
    for msg in history:
        if msg["role"] in ("user", "assistant"):
            extraction_messages.append({"role": msg["role"], "content": msg["content"]})

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=extraction_messages,
            temperature=0.0,
            max_tokens=500,
        )
        text = resp.choices[0].message.content or ""
        # Try to parse as JSON directly
        text = text.strip()
        if text.startswith("```"):
            # Strip markdown code fences
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        return json.loads(text)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Planning kick-off (calls the backend API)
# ---------------------------------------------------------------------------

def _kick_off_planning(plan: dict) -> str | None:
    """POST to /trips, stream SSE progress into the chat, return session_id."""
    url = _api_url()

    payload = {
        "user_query": plan.get("user_query", "Plan a trip"),
        "constraints": plan.get("constraints", {}),
        "mode": "autonomous",
    }

    # Create the trip
    try:
        resp = requests.post(f"{url}/trips", json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        session_id = data["session_id"]
    except Exception as exc:
        st.error(f"Failed to start planning: {exc}")
        return None

    # Stream SSE progress
    progress_placeholder = st.empty()
    status_lines: list[str] = []

    try:
        import sseclient

        sse_resp = requests.get(
            f"{url}/trips/{session_id}/stream",
            stream=True,
            timeout=300,
        )
        client = sseclient.SSEClient(sse_resp)

        for event in client.events():
            try:
                payload = json.loads(event.data)
            except json.JSONDecodeError:
                continue

            evt = payload.get("event", "")

            if evt == "agent_start":
                node = payload.get("node", "")
                label = _pretty_node(node)
                status_lines.append(f"⏳ {label}...")
                progress_placeholder.markdown("\n\n".join(status_lines))

            elif evt == "agent_complete":
                node = payload.get("node", "")
                label = _pretty_node(node)
                # Replace the "working" line with "done"
                status_lines = [
                    line.replace(f"⏳ {label}...", f"✅ {label}")
                    if label in line else line
                    for line in status_lines
                ]
                progress_placeholder.markdown("\n\n".join(status_lines))

            elif evt == "graph_complete":
                status_lines.append("\n🎉 **Planning complete!**")
                progress_placeholder.markdown("\n\n".join(status_lines))
                break

            elif evt == "error":
                msg = payload.get("message", "Unknown error")
                status_lines.append(f"\n❌ Error: {msg}")
                progress_placeholder.markdown("\n\n".join(status_lines))
                break

    except Exception as exc:
        st.warning(f"Could not stream progress (planning continues in background): {exc}")

    return session_id


# ---------------------------------------------------------------------------
# Render completed trip results
# ---------------------------------------------------------------------------

def _show_trip_results(session_id: str) -> str:
    """Fetch the completed trip and return a formatted results string."""
    url = _api_url()
    try:
        resp = requests.get(f"{url}/trips/{session_id}", timeout=15)
        resp.raise_for_status()
        trip = resp.json()
    except Exception as exc:
        return f"Could not fetch trip results: {exc}"

    return _render_results(trip)


def _render_results(trip: Any) -> str:
    """Turn a trip dict into a rich Markdown string."""
    def _coerce_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    trip = _coerce_dict(trip)
    raw_state = _coerce_dict(trip.get("raw_state"))

    parts: list[str] = []
    parts.append("## 🎉 Your Trip is Ready!\n")

    # --- Itinerary ---
    itinerary = _coerce_dict(trip.get("itinerary"))

    # Handle both raw_state nested and top-level itinerary
    if not itinerary:
        itinerary = _coerce_dict(raw_state.get("itinerary"))

    daily = itinerary.get("daily_plans") or itinerary.get("days") or []
    if daily:
        parts.append("### 📋 Daily Itinerary\n")
        for day in daily:
            day_num = day.get("day_number", day.get("day", "?"))
            theme = day.get("theme") or day.get("title") or ""
            parts.append(f"#### Day {day_num}: {theme}\n")

            for slot, icon in [("morning", "🌅"), ("afternoon", "☀️"), ("evening", "🌙")]:
                activities = day.get(slot) or []
                if not activities:
                    continue
                parts.append(f"**{icon} {slot.title()}**\n")
                for act in activities:
                    if isinstance(act, str):
                        parts.append(f"- {act}")
                        continue
                    name = act.get("name") or act.get("activity", "Activity")
                    loc = act.get("location", "")
                    cost = act.get("estimated_cost") or act.get("cost", "")
                    tip = act.get("tips") or act.get("tip", "")
                    line = f"- **{name}**"
                    if loc:
                        line += f"  📍 {loc}"
                    if cost:
                        cost_text = f"${cost}" if isinstance(cost, (int, float)) else str(cost)
                        line += f"  💰 {cost_text}"
                    parts.append(line)
                    if tip:
                        parts.append(f"  💡 *{tip}*")
                parts.append("")

    # --- Booking summary ---
    booking = _coerce_dict(trip.get("booking"))
    if not booking:
        booking = _coerce_dict(raw_state.get("booking_result"))

    if booking:
        parts.append("### Booking Summary\n")

        # Status and reference
        status = booking.get("status", "unknown")
        ref = booking.get("booking_reference", "")
        if ref:
            parts.append(f"**Reference:** {ref}")
        parts.append(f"**Status:** {status}\n")

        # LLM-generated summary
        summary = booking.get("summary")
        if summary:
            parts.append(f"{summary}\n")

        # Price breakdown
        total = booking.get("total_estimated_usd")
        if total:
            parts.append(f"**Total Estimated Cost:** ${total:,.2f}")
        breakdown = booking.get("price_breakdown") or {}
        if breakdown:
            for label, key in [
                ("Flights", "flights_usd"),
                ("Hotel", "hotel_usd"),
                ("Activities", "activities_usd"),
                ("Food", "food_usd"),
                ("Transport", "transport_usd"),
            ]:
                val = breakdown.get(key)
                if val:
                    parts.append(f"  - {label}: ${val:,.2f}")
        parts.append("")

        # Flight details
        fb = _coerce_dict(booking.get("flight_booking"))
        if fb and fb.get("airline"):
            parts.append(
                f"**Flight:** {fb.get('airline', 'N/A')} — "
                f"${fb.get('price_usd', 0):,.2f}"
            )

        # Hotel details
        hb = _coerce_dict(booking.get("hotel_booking"))
        if hb and hb.get("name"):
            parts.append(
                f"**Hotel:** {hb.get('name', 'N/A')} — "
                f"${hb.get('price_per_night_usd', 0):,.2f}/night"
            )

        # Booking instructions only if not budget_exceeded
        if status != "budget_exceeded":
            instructions = booking.get("booking_instructions") or []
            if instructions:
                parts.append("\n**Next Steps:**")
                for line in instructions:
                    if isinstance(line, str) and line.strip():
                        parts.append(f"  - {line}")

            # Real booking flag
            if not booking.get("is_real_booking"):
                parts.append(
                    "\n*This is a pre-booking plan. Complete reservations using the "
                    "steps above.*"
                )

    if not daily and not booking:
        parts.append("The trip was planned but no detailed itinerary is available yet.")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def render():
    st.title("✈️ Plan Your Trip")
    st.caption("Chat with your AI travel agent — just describe your dream trip!")

    # ── Session state init ──────────────────────────────────────────────
    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = [
            {"role": "assistant", "content": _GREETING}
        ]
    if "openai_history" not in st.session_state:
        # Full OpenAI message history including system prompt
        st.session_state["openai_history"] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "assistant", "content": _GREETING},
        ]
    if "planning_done" not in st.session_state:
        st.session_state["planning_done"] = False
    if "current_session_id" not in st.session_state:
        st.session_state["current_session_id"] = None

    # ── Display chat history ────────────────────────────────────────────
    for msg in st.session_state["chat_messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ── Chat input ──────────────────────────────────────────────────────
    if prompt := st.chat_input("Tell me about your dream trip..."):
        # Show user message
        st.session_state["chat_messages"].append({"role": "user", "content": prompt})
        st.session_state["openai_history"].append({"role": "user", "content": prompt})

        with st.chat_message("user"):
            st.markdown(prompt)

        # Count user turns (excluding system prompt and greeting)
        user_turn_count = sum(
            1 for m in st.session_state["openai_history"] if m["role"] == "user"
        )

        # If 6+ user turns and still no plan, inject a nudge to force handoff
        if user_turn_count >= 6 and not st.session_state["planning_done"]:
            st.session_state["openai_history"].append({
                "role": "system",
                "content": (
                    "You now have enough information. You MUST include the "
                    "<!--PLAN_JSON ... PLAN_JSON--> block in your VERY NEXT "
                    "response. Fill in reasonable defaults for anything missing. "
                    "Do NOT ask more questions."
                ),
            })

        # Get AI response (streaming)
        with st.chat_message("assistant"):
            client = _get_openai()
            message_placeholder = st.empty()
            full_response = ""

            try:
                stream = client.chat.completions.create(
                    model="gpt-4o",
                    messages=st.session_state["openai_history"],
                    stream=True,
                    temperature=0.7,
                    max_tokens=2000,
                )

                for chunk in stream:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        full_response += delta.content
                        # Show text without the hidden JSON block
                        display_text = _strip_plan_block(full_response)
                        message_placeholder.markdown(display_text + "▌")

                # Final display without cursor
                display_text = _strip_plan_block(full_response)
                message_placeholder.markdown(display_text)

            except Exception as exc:
                full_response = f"Sorry, I encountered an error: {exc}"
                message_placeholder.markdown(full_response)

        # Save to history
        st.session_state["chat_messages"].append(
            {"role": "assistant", "content": _strip_plan_block(full_response)}
        )
        st.session_state["openai_history"].append(
            {"role": "assistant", "content": full_response}
        )

        # Check if the AI included a plan JSON
        plan = _extract_plan(full_response)

        # Fallback: if 3+ user turns and LLM still didn't include the block,
        if not plan and user_turn_count >= 6 and not st.session_state["planning_done"]:
            plan = _force_extract_plan(client, st.session_state["openai_history"])

        if plan and not st.session_state["planning_done"]:
            with st.chat_message("assistant"):
                st.markdown("⚡ **Starting the planning agents now...**\n")
                session_id = _kick_off_planning(plan)

                if session_id:
                    st.session_state["current_session_id"] = session_id
                    st.session_state["planning_done"] = True

                    # Fetch and display results
                    # Small delay to let DB commit
                    time.sleep(1)
                    results_text = _show_trip_results(session_id)
                    st.markdown(results_text)

                    # Save results message to chat
                    st.session_state["chat_messages"].append(
                        {"role": "assistant", "content": results_text}
                    )

    # ── New trip button ────────────────────────────────────────────────
    if st.session_state["planning_done"]:
        st.divider()
        if st.button("🔄 Plan Another Trip", use_container_width=True):
            st.session_state["chat_messages"] = [
                {"role": "assistant", "content": _GREETING}
            ]
            st.session_state["openai_history"] = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "assistant", "content": _GREETING},
            ]
            st.session_state["planning_done"] = False
            st.session_state["current_session_id"] = None
            st.rerun()


if __name__ == "__main__":
    st.session_state.setdefault(
        "api_url",
        os.getenv("FASTAPI_BASE_URL", os.getenv("API_URL", "http://localhost:8000")),
    )
    render()
