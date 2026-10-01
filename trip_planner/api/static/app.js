// Trip planner web UI. Plain JS, no build step.
"use strict";

const $ = (sel) => document.querySelector(sel);
const log = $("#log"), input = $("#input"), send = $("#send"), panel = $("#panel");
let tripId = location.hash.slice(1) || null;
let busy = false;

// ── Helpers ────────────────────────────────────────────────────────────────

// Build DOM nodes without innerHTML so trip data can never inject markup.
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  node.append(...children.flat().filter((c) => c != null && c !== false));
  return node;
}

const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : null);
const link = (text, url) =>
  safeUrl(url) ? el("a", { href: url, target: "_blank", rel: "noopener" }, text) : text;
const usd = (n) => (n == null ? "–" : "$" + Math.round(n).toLocaleString());
const hhmm = (t) => (t || "").slice(0, 5);
const fmtTime = (dt) => (dt ? new Date(dt).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "");

// Plain text with http(s) URLs turned into links.
function linkify(text) {
  return text.split(/(https?:\/\/[^\s)]+)/g).map((part, i) => (i % 2 ? link(part, part) : part));
}

// ── API ────────────────────────────────────────────────────────────────────

async function api(path, opts = {}) {
  const key = localStorage.getItem("apiKey");
  const headers = { "Content-Type": "application/json", ...(key ? { Authorization: `Bearer ${key}` } : {}) };
  const resp = await fetch(path, { ...opts, headers });
  if (resp.status === 401) {
    const entered = prompt("API key for this planner:");
    if (entered) {
      localStorage.setItem("apiKey", entered.trim());
      return api(path, opts);
    }
  }
  if (!resp.ok) {
    let detail = resp.statusText;
    try { detail = (await resp.json()).detail || detail; } catch {}
    throw new Error(`${resp.status}: ${detail}`);
  }
  return resp;
}

// POST and read the SSE body (EventSource can't POST).
async function stream(path, body) {
  setBusy(true);
  let bubble = null, text = "";
  const chips = [];
  try {
    const resp = await api(path, { method: "POST", body: JSON.stringify(body) });
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let cut;
      while ((cut = buf.indexOf("\n\n")) >= 0) {
        const chunk = buf.slice(0, cut);
        buf = buf.slice(cut + 2);
        if (!chunk.startsWith("data: ")) continue;
        const ev = JSON.parse(chunk.slice(6));
        if (ev.type === "text") {
          if (!bubble) bubble = addMsg("assistant", "");
          text += ev.delta;
          bubble.replaceChildren(...linkify(text));
        } else if (ev.type === "tool_start") {
          bubble = null; text = "";  // text after a tool call starts a new bubble
          const chip = addChip("⏳ " + ev.label);
          chip.dataset.name = ev.name;
          chip.dataset.label = ev.label;
          chips.push(chip);
        } else if (ev.type === "tool_end") {
          const chip = chips.find((c) => c.dataset.name === ev.name && !c.dataset.done);
          if (chip) {
            chip.dataset.done = "1";
            chip.textContent = ev.ok ? "✓ " + chip.dataset.label : `✗ ${chip.dataset.label}: ${ev.summary}`;
            if (!ev.ok) chip.classList.add("fail");
          }
        } else if (ev.type === "trip") {
          renderPanel(ev);
          loadTrips();
        } else if (ev.type === "approval") {
          addApproval(ev);
        } else if (ev.type === "error") {
          addMsg("error", "Something went wrong: " + ev.message);
        }
        scrollDown();
      }
    }
  } catch (e) {
    addMsg("error", e.message);
  } finally {
    setBusy(false);
  }
}

// ── Chat ───────────────────────────────────────────────────────────────────

function setBusy(on) {
  busy = on;
  input.disabled = send.disabled = on || !tripId;
  if (!on && tripId) input.focus();
}

function scrollDown() { log.scrollTop = log.scrollHeight; }

function addMsg(role, text) {
  $("#hint")?.remove();
  const node = el("div", { class: "msg " + role }, ...linkify(text));
  log.append(node);
  scrollDown();
  return node;
}

function addChip(label) {
  const node = el("div", { class: "chip" }, label);
  log.append(node);
  return node;
}

function addApproval({ summary, total_usd }) {
  const note = el("textarea", { rows: 2, "aria-label": "What should change?", placeholder: "What should change?" });
  const card = el("div", { class: "approval" },
    el("strong", {}, "Ready to book?"),
    el("p", {}, summary),
    el("p", {}, "Total: ", el("strong", {}, usd(total_usd))),
    note,
    el("div", { class: "actions" },
      el("button", { type: "button", class: "primary", onclick: () => answer(true) }, "Approve"),
      el("button", { type: "button", onclick: () => answer(false) }, "Request changes")));
  function answer(approved) {
    if (!approved && !note.value.trim()) { note.focus(); return; }
    card.remove();
    addMsg("user", approved ? "Approved." : "Changes: " + note.value.trim());
    stream(`/trips/${tripId}/approval`, { approved, note: note.value.trim() });
  }
  log.append(card);
  scrollDown();
}

$("#composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text || busy || !tripId) return;
  input.value = "";
  addMsg("user", text);
  stream(`/trips/${tripId}/messages`, { text });
});

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    $("#composer").requestSubmit();
  }
});

// ── Trips sidebar ──────────────────────────────────────────────────────────

async function loadTrips() {
  let trips = [];
  try { trips = await (await api("/trips")).json(); } catch (e) { return; }
  $("#trips").replaceChildren(...trips.map((t) =>
    el("li", {},
      el("a", { href: "#" + t.id, "aria-current": t.id === tripId ? "true" : null },
        t.title || "Untitled trip", el("small", {}, t.status.replace("_", " "))),
      el("button", { type: "button", class: "delete", "aria-label": `Delete ${t.title || "trip"}`,
        onclick: () => deleteTrip(t.id) }, "Delete"))));
}

async function deleteTrip(id) {
  if (!confirm("Delete this trip?")) return;
  try { await api(`/trips/${id}`, { method: "DELETE" }); } catch (e) { addMsg("error", e.message); }
  if (id === tripId) location.hash = "";
  loadTrips();
}

$("#new-trip").addEventListener("click", async () => {
  try {
    const { id } = await (await api("/trips", { method: "POST" })).json();
    location.hash = id;
  } catch (e) { addMsg("error", e.message); }
});

async function openTrip() {
  tripId = location.hash.slice(1) || null;
  log.replaceChildren();
  panel.replaceChildren();
  setBusy(false);
  loadTrips();
  if (!tripId) {
    log.append(el("p", { class: "empty", id: "hint" }, "Create or pick a trip, then tell the planner where you want to go."));
    return;
  }
  try {
    const data = await (await api(`/trips/${tripId}`)).json();
    for (const m of data.messages || []) addMsg(m.role, m.text);
    renderPanel(data);
    if (data.pending_approval) addApproval(data.pending_approval);
    if (!data.messages?.length) log.append(el("p", { class: "empty", id: "hint" }, "Where do you want to go?"));
  } catch (e) {
    addMsg("error", e.message);
  }
}

window.addEventListener("hashchange", openTrip);

// ── Trip panel ─────────────────────────────────────────────────────────────

function renderPanel({ trip, issues = [], cost }) {
  if (!trip) return;
  const dates = trip.start_date ? `${trip.start_date} → ${trip.end_date || "?"}` : "Dates not set";
  const parts = [
    el("h2", {}, trip.title || "Untitled trip"),
    el("p", { class: "muted" },
      [dates, `${trip.travelers} traveler${trip.travelers > 1 ? "s" : ""}`, `${trip.pace} pace`, trip.tier].join(" · ")),
  ];

  if (cost) parts.push(budgetBar(cost));

  if (trip.flight) {
    const f = trip.flight;
    parts.push(el("h3", {}, "Flight"), el("div", { class: "card" },
      el("strong", {}, `${f.airline} · ${f.origin} → ${f.destination}`),
      el("div", {}, `${fmtTime(f.depart_at)} → ${fmtTime(f.arrive_at)}`),
      el("div", { class: "muted" },
        `${f.stops ? f.stops + " stop" + (f.stops > 1 ? "s" : "") : "Nonstop"}` +
        (f.return_date ? ` · return ${f.return_date}` : "")),
      el("div", {}, el("strong", {}, usd(f.price_usd)), " ", link("Book flight", f.booking_url))));
  }

  if (trip.hotel) {
    const h = trip.hotel;
    const rating = [h.stars ? "★".repeat(h.stars) : "", h.rating ? `${h.rating}/5` : ""].filter(Boolean).join(" ");
    parts.push(el("h3", {}, "Hotel"), el("div", { class: "card" },
      el("strong", {}, h.name), rating && el("span", { class: "muted" }, " " + rating),
      el("div", { class: "muted" }, `${h.check_in} → ${h.check_out}`),
      el("div", {}, `${usd(h.price_per_night_usd)}/night · `, el("strong", {}, usd(h.total_usd) + " total"), " ",
        link("Book hotel", h.booking_url))));
  }

  if (issues.length) {
    parts.push(el("h3", {}, "Issues"));
    for (const sev of ["error", "warning"]) {
      const list = issues.filter((i) => i.severity === sev);
      if (list.length) parts.push(el("ul", { class: "issues " + sev, "aria-label": sev + "s" },
        list.map((i) => el("li", {}, i.date ? el("a", { href: "#" + tripId, onclick: (e) => jumpToDay(e, i.date) }, i.message) : i.message))));
    }
  }

  if (trip.days?.length) {
    parts.push(el("h3", {}, "Days"));
    trip.days.forEach((d, n) => parts.push(dayCard(d, n)));
  }

  panel.replaceChildren(...parts);
}

function budgetBar(cost) {
  const total = cost.total || 0, budget = cost.budget;
  const over = budget != null && total > budget;
  const pct = budget ? Math.min(100, (total / budget) * 100) : 0;
  return el("div", { class: "card" },
    el("div", { class: over ? "over-text" : "" },
      el("strong", {}, usd(total)), budget != null ? ` of ${usd(budget)} budget` : " estimated (no budget set)"),
    budget != null && el("div", { class: "bar" + (over ? " over" : ""), role: "img",
      "aria-label": `${Math.round((total / budget) * 100)}% of budget` }, el("span", { style: `width:${pct}%` })),
    el("div", { class: "muted" },
      `Flight ${usd(cost.flight)} · Hotel ${usd(cost.hotel)} · Activities ${usd(cost.activities)}`));
}

const MODE_ICON = { walk: "🚶", transit: "🚇", drive: "🚗" };

function dayCard(day, n) {
  return el("div", { class: "card day", id: "day-" + day.date },
    el("strong", {}, `Day ${n + 1} · ${day.date}`), day.area && el("span", { class: "muted" }, " · " + day.area),
    day.notes && el("div", { class: "muted" }, day.notes),
    el("ol", {}, day.stops.map((s) => el("li", {},
      s.travel_from_prev_min != null &&
        el("div", { class: "travel" }, `${MODE_ICON[s.travel_mode] || "→"} ${s.travel_from_prev_min} min`),
      el("div", {}, el("strong", {}, hhmm(s.start)), " ", link(s.place.name, s.place.maps_url)),
      el("div", { class: "stop-meta" },
        [`${s.duration_min} min`, s.est_cost_usd != null ? `~${usd(s.est_cost_usd)}` : ""].filter(Boolean).join(" · ")),
      s.note && el("div", {}, s.note)))));
}

function jumpToDay(e, date) {
  e.preventDefault();
  document.getElementById("day-" + date)?.scrollIntoView({ behavior: "smooth" });
}

openTrip();
