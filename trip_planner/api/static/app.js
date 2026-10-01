// Wayfarer trip planner web UI. Plain JS, no build step.
"use strict";

const $ = (sel) => document.querySelector(sel);
const log = $("#log"), input = $("#input"), send = $("#send"), panel = $("#panel");
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
let tripId = location.hash.slice(1) || null;
let busy = false;
let pendingText = null;      // hero prompt waiting for its new trip to open
let seenBlocks = new Set();  // panel blocks already revealed, so re-renders don't re-animate

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

const SVG_NS = "http://www.w3.org/2000/svg";
function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) node.setAttribute(k, v);
  node.append(...children.flat().filter(Boolean));
  return node;
}
// Small inline icon from a path string.
const icon = (d, cls) => svg("svg", { viewBox: "0 0 24 24", "aria-hidden": "true", class: cls }, svg("path", { d }));
const ICONS = {
  plane: "M2 12h20M14 5l7 7-7 7M6 9l2 3-2 3",
  bed: "M3 18V7M3 13h18v5M21 13a3 3 0 0 0-3-3h-7v3M7 10.5a1.5 1.5 0 1 0 0 .01",
  x: "M6 6l12 12M18 6L6 18",
};

const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : null);
const link = (text, url, cls) =>
  safeUrl(url) ? el("a", { href: url, target: "_blank", rel: "noopener", class: cls }, text) : text;
const usd = (n) => (n == null ? "–" : "$" + Math.round(n).toLocaleString());
const hhmm = (t) => (t || "").slice(0, 5);
// Departure/arrival: big 24h time over a small date.
const passTime = (dt) => {
  if (!dt) return "";
  const d = new Date(dt);
  return [el("b", {}, d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false })),
    el("small", {}, d.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" }))];
};
const fmtDate = (d, opts = { weekday: "short", month: "short", day: "numeric" }) =>
  d ? new Date(d + "T00:00").toLocaleDateString([], opts) : "";
const pad2 = (n) => String(n).padStart(2, "0");

// Plain text with http(s) URLs turned into links and **bold** spans.
function inline(text) {
  return text.split(/(\*\*[^*]+\*\*|https?:\/\/[^\s)]+)/g).map((part, i) => {
    if (!(i % 2)) return part;
    return part.startsWith("**") ? el("strong", {}, part.slice(2, -2)) : link(part, part);
  });
}

// Tiny markdown subset for planner replies: paragraphs, bullet/numbered lists, headings.
function markdown(text) {
  const out = [];
  let list = null;
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*(?:[-*•]|(\d+)[.)])\s+(.*)/);
    if (bullet) {
      const tag = bullet[1] ? "ol" : "ul";
      if (!list || list.tagName.toLowerCase() !== tag) out.push((list = el(tag)));
      list.append(el("li", {}, inline(bullet[2])));
      continue;
    }
    list = null;
    if (!line.trim()) continue;
    const head = line.match(/^#{1,4}\s+(.*)/);
    out.push(head ? el("h4", {}, inline(head[1])) : el("p", {}, inline(line)));
  }
  return out.length ? out : [el("p")];
}

function toast(text) {
  const t = el("div", { class: "toast", role: "status" }, text);
  $("#toasts").append(t);
  setTimeout(() => t.remove(), 3300);
}

// Promise-based <dialog>: resolves to the input value (or true) on OK, null on cancel.
function ask({ title, text = "", okLabel = "OK", secret = false }) {
  const dlg = $("#dialog"), field = $("#dialog-input");
  $("#dialog-title").textContent = title;
  $("#dialog-text").textContent = text;
  $("#dialog-ok").textContent = okLabel;
  field.hidden = !secret;
  field.value = "";
  dlg.returnValue = "";
  dlg.showModal();
  if (secret) field.focus();
  return new Promise((resolve) => {
    dlg.addEventListener("close", () =>
      resolve(dlg.returnValue === "ok" ? (secret ? field.value.trim() : true) : null), { once: true });
  });
}

function withTransition(fn) {
  if (document.startViewTransition && !reduceMotion) document.startViewTransition(fn);
  else fn();
}

// ── API ────────────────────────────────────────────────────────────────────

let keyPrompt = null;

async function api(path, opts = {}) {
  const key = localStorage.getItem("apiKey");
  const headers = { "Content-Type": "application/json", ...(key ? { Authorization: `Bearer ${key}` } : {}) };
  const resp = await fetch(path, { ...opts, headers });
  if (resp.status === 401) {
    // Parallel requests share one prompt (showModal throws if already open).
    keyPrompt ||= ask({ title: "API key needed", text: "This planner is protected. Enter its API key.", okLabel: "Unlock", secret: true })
      .finally(() => setTimeout(() => (keyPrompt = null)));
    const entered = await keyPrompt;
    if (entered) {
      localStorage.setItem("apiKey", entered);
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
  let bubble = null, text = "", trail = null, frame = 0;
  const chips = [];
  let thinking = addThinking();
  const settle = () => { thinking?.remove(); thinking = null; };
  const paint = () => {
    frame = 0;
    if (bubble) { bubble.replaceChildren(...markdown(text)); scrollDown(); }
  };
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
          settle();
          if (!bubble) { bubble = addMsg("assistant", ""); bubble.classList.add("streaming"); trail = null; }
          text += ev.delta;
          frame ||= requestAnimationFrame(paint);
        } else if (ev.type === "tool_start") {
          settle();
          if (bubble) { paint(); bubble.classList.remove("streaming"); }
          bubble = null; text = "";  // text after a tool call starts a new bubble
          if (!trail) { trail = el("div", { class: "trail", "aria-label": "Planner activity" }); log.append(trail); }
          const chip = el("div", { class: "chip" }, el("span", { class: "dot" }), el("span", { class: "label" }, ev.label));
          chip.dataset.name = ev.name;
          trail.append(chip);
          chips.push(chip);
          thinking = addThinking();
        } else if (ev.type === "tool_end") {
          const chip = chips.find((c) => c.dataset.name === ev.name && !c.dataset.done);
          if (chip) {
            chip.dataset.done = "1";
            chip.classList.add(ev.ok ? "done" : "fail");
            if (!ev.ok) chip.querySelector(".label").append(`: ${ev.summary}`);
            if (ev.ms >= 1000) chip.append(el("span", { class: "took" }, `· ${(ev.ms / 1000).toFixed(1)}s`));
          }
        } else if (ev.type === "trip") {
          renderPanel(ev);
          loadTrips();
        } else if (ev.type === "approval") {
          settle();
          addApproval(ev);
        } else if (ev.type === "error") {
          settle();
          addMsg("error", "Something went wrong: " + ev.message);
        }
        scrollDown();
      }
    }
  } catch (e) {
    addMsg("error", e.message);
  } finally {
    cancelAnimationFrame(frame);
    paint();
    bubble?.classList.remove("streaming");
    settle();
    setBusy(false);
  }
}

// ── Chat ───────────────────────────────────────────────────────────────────

function setBusy(on) {
  busy = on;
  document.body.classList.toggle("busy", on);
  input.disabled = on || !tripId;
  send.disabled = on || !tripId || !input.value.trim();
  if (!on && tripId && matchMedia("(pointer: fine)").matches) input.focus();
}

function scrollDown() { log.scrollTop = log.scrollHeight; }

function addMsg(role, text) {
  log.querySelector(".empty")?.remove();
  const node = el("div", { class: "msg " + role }, ...(role === "assistant" ? markdown(text) : inline(text)));
  log.append(node);
  scrollDown();
  return node;
}

function addThinking() {
  const node = el("div", { class: "thinking", "aria-label": "Planner is thinking" }, el("i"), el("i"), el("i"));
  log.append(node);
  scrollDown();
  return node;
}

function emptyChat() {
  const ideas = ["Long weekend in Kyoto in April, 2 people", "A week in Mexico City for food lovers, ~$2500", "Relaxed 4 days in Lisbon with lots of walking"];
  return el("div", { class: "empty" },
    el("strong", {}, "Where to?"),
    "Tell the planner a destination, dates, who’s coming and a rough budget.",
    el("div", { class: "suggestions" }, ideas.map((t) =>
      el("button", { type: "button", onclick: () => { input.value = t; autosize(); input.focus(); syncSend(); } }, t))));
}

function addApproval({ summary, total_usd }) {
  const note = el("textarea", { rows: 2, "aria-label": "What should change?", placeholder: "Or tell the planner what to change…" });
  const card = el("div", { class: "approval" },
    el("div", { class: "kicker" }, "Ready for review"),
    el("h3", {}, "Your itinerary is ready to book"),
    el("div", {}, ...markdown(summary)),
    el("div", { class: "total" }, usd(total_usd), el("small", {}, "estimated total")),
    note,
    el("div", { class: "actions" },
      el("button", { type: "button", class: "btn", onclick: () => answer(false) }, "Request changes"),
      el("button", { type: "button", class: "btn primary", onclick: () => answer(true) }, "Approve plan")));
  function answer(approved) {
    const text = note.value.trim();
    if (!approved && !text) { note.focus(); toast("Tell the planner what to change"); return; }
    card.querySelectorAll("button, textarea").forEach((b) => (b.disabled = true));
    const go = () => {
      card.remove();
      addMsg("user", approved ? "Approved." : "Changes: " + text);
      stream(`/trips/${tripId}/approval`, { approved, note: text });
    };
    if (approved && !reduceMotion) { card.classList.add("stamped"); setTimeout(go, 900); } else go();
  }
  log.append(card);
  scrollDown();
}

function sendText(text) {
  addMsg("user", text);
  stream(`/trips/${tripId}/messages`, { text });
}

const syncSend = () => { send.disabled = busy || !tripId || !input.value.trim(); };
function autosize() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 180) + "px";
}

$("#composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text || busy || !tripId) return;
  input.value = "";
  autosize();
  sendText(text);
});

input.addEventListener("input", () => { autosize(); syncSend(); });
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    $("#composer").requestSubmit();
  }
});

// ── Trips sidebar ──────────────────────────────────────────────────────────

async function loadTrips() {
  let trips = [];
  try { trips = await (await api("/trips")).json(); } catch { return; }
  const items = trips.map((t, i) =>
    el("li", { style: `--i:${i}` },
      el("a", { href: "#" + t.id, "aria-current": t.id === tripId ? "true" : null },
        el("span", { class: "trip-name" }, t.title || "Untitled trip"),
        el("span", { class: "status " + t.status }, t.status.replace("_", " "))),
      el("button", { type: "button", class: "delete", "aria-label": `Delete ${t.title || "trip"}`,
        onclick: () => deleteTrip(t) }, icon(ICONS.x))));
  $("#trips").replaceChildren(...(items.length ? items : [el("li", { class: "rail-empty" }, "No trips yet. Start one above.")]));
}

async function deleteTrip(t) {
  if (!(await ask({ title: "Delete this trip?", text: `“${t.title || "Untitled trip"}” and its conversation will be gone for good.`, okLabel: "Delete" }))) return;
  try { await api(`/trips/${t.id}`, { method: "DELETE" }); toast("Trip deleted"); } catch (e) { toast(e.message); }
  if (t.id === tripId) location.hash = "";
  loadTrips();
}

async function newTrip(text) {
  try {
    const { id } = await (await api("/trips", { method: "POST" })).json();
    pendingText = text || null;
    closeNav();
    location.hash = id;
  } catch (e) { toast(e.message); }
}

$("#new-trip").addEventListener("click", () => newTrip());

async function openTrip() {
  tripId = location.hash.slice(1) || null;
  seenBlocks = new Set();
  document.body.dataset.state = tripId ? "trip" : "landing";
  document.body.dataset.view = "chat";
  syncViewToggle();
  $("#topbar-title").textContent = tripId ? "Loading…" : "New journey";
  log.replaceChildren();
  panel.replaceChildren(panelEmpty());
  setBusy(false);
  loadTrips();
  if (!tripId) return;
  try {
    const data = await (await api(`/trips/${tripId}`)).json();
    for (const m of data.messages || []) addMsg(m.role, m.text);
    renderPanel(data);
    if (data.pending_approval) addApproval(data.pending_approval);
    if (pendingText) { sendText(pendingText); pendingText = null; }
    else if (!data.messages?.length) log.append(emptyChat());
  } catch (e) {
    addMsg("error", e.message);
  }
}

window.addEventListener("hashchange", () => withTransition(openTrip));

// Mobile: off-canvas trips + chat/itinerary toggle.
function closeNav() {
  document.body.classList.remove("nav-open");
  $("#scrim").hidden = true;
  $("#menu").setAttribute("aria-expanded", "false");
}
$("#menu").addEventListener("click", () => {
  document.body.classList.add("nav-open");
  $("#scrim").hidden = false;
  $("#menu").setAttribute("aria-expanded", "true");
});
$("#scrim").addEventListener("click", closeNav);
$("#trips").addEventListener("click", (e) => { if (e.target.closest("a")) closeNav(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeNav(); });

function syncViewToggle() {
  for (const b of document.querySelectorAll(".view-toggle button"))
    b.setAttribute("aria-selected", String(b.dataset.view === document.body.dataset.view));
}
document.querySelector(".view-toggle").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  document.body.dataset.view = b.dataset.view;
  syncViewToggle();
  if (b.dataset.view === "panel") revealVisible();
});

// ── Landing hero ───────────────────────────────────────────────────────────

const POSTCARDS = [
  { city: "Lisbon", line: "Tiles, trams & pastéis", code: "LIS", bg: "linear-gradient(170deg,#f2b880 0%,#e2725b 55%,#7a3b4f 100%)", sun: "#ffe7b0", hill: "#5c2b3b", prompt: "5 days in Lisbon in May for 2 people, ~$3000, love food and viewpoints" },
  { city: "Kyoto", line: "Temples in slow light", code: "KIX", bg: "linear-gradient(170deg,#f7d6c7 0%,#c98a9b 50%,#4b3a5c 100%)", sun: "#fff1e6", hill: "#2f2440", prompt: "A relaxed week in Kyoto in April, 2 people, temples, gardens and tea" },
  { city: "Oaxaca", line: "Mezcal & markets", code: "OAX", bg: "linear-gradient(170deg,#ffd27a 0%,#e8833a 50%,#8a3324 100%)", sun: "#fff3c4", hill: "#4e1f17", prompt: "4 days in Oaxaca for a food-obsessed couple, mid budget, markets and mezcal" },
  { city: "Reykjavík", line: "Fire, ice & hot springs", code: "KEF", bg: "linear-gradient(170deg,#bfe0dc 0%,#4f8f94 50%,#1d3340 100%)", sun: "#eaf7f2", hill: "#0f1e27", prompt: "6 days around Reykjavík in September, 2 people, hot springs and day hikes, ~$4000" },
];

function renderPostcards() {
  $("#postcards").replaceChildren(...POSTCARDS.map((p, i) => {
    const hills = svg("svg", { class: "pc-hills", viewBox: "0 0 200 120", preserveAspectRatio: "none", "aria-hidden": "true" },
      svg("path", { d: "M0 70 Q40 30 80 60 T160 50 T200 60 V120 H0Z", fill: p.hill, opacity: ".55" }),
      svg("path", { d: "M0 90 Q50 60 100 85 T200 80 V120 H0Z", fill: p.hill }));
    const card = el("button", { type: "button", class: "postcard", style: `--i:${i};--bg:${p.bg};--sunc:${p.sun}`, "aria-label": `Plan a trip to ${p.city}` },
      el("span", { class: "pc-sun" }), hills,
      el("span", { class: "pc-stamp" }, p.code, el("br"), "✈"),
      el("span", { class: "pc-city" }, p.city),
      el("span", { class: "pc-line" }, p.line));
    card.addEventListener("pointermove", (e) => {
      if (reduceMotion) return;
      const r = card.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
      card.style.setProperty("--ry", `${(x - 0.5) * 14}deg`);
      card.style.setProperty("--rx", `${(0.5 - y) * 14}deg`);
      card.style.setProperty("--mx", `${x * 100}%`);
      card.style.setProperty("--my", `${y * 100}%`);
    });
    card.addEventListener("pointerleave", () => { card.style.setProperty("--rx", "0deg"); card.style.setProperty("--ry", "0deg"); });
    card.addEventListener("click", () => typeInto($("#hero-input"), p.prompt));
    return card;
  }));
}

// Type text into an input like a person would, then focus it.
let typing = 0;
function typeInto(field, text) {
  const run = ++typing;
  field.focus();
  if (reduceMotion) { field.value = text; return; }
  let n = 0;
  (function tick() {
    if (run !== typing) return;
    field.value = text.slice(0, ++n);
    if (n < text.length) setTimeout(tick, 12 + Math.random() * 18);
  })();
}

// Rotating placeholder ideas.
const IDEAS = ["5 days in Lisbon in May, 2 people, ~$3000", "Weekend in Paris for a birthday, packed pace", "Tokyo & Kyoto in spring, 10 days, mid budget", "Family week in Barcelona, beaches + Gaudí"];
let ideaIdx = 0;
setInterval(() => {
  const f = $("#hero-input");
  if (document.body.dataset.state === "landing" && !f.value && document.activeElement !== f)
    f.placeholder = IDEAS[++ideaIdx % IDEAS.length];
}, 3200);

$("#hero-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const f = $("#hero-input"), text = f.value.trim();
  if (!text) { f.focus(); toast("Describe a trip to get started"); return; }
  f.value = "";
  newTrip(text);
});

// ── Trip panel ─────────────────────────────────────────────────────────────

const io = new IntersectionObserver((entries) => {
  for (const e of entries) if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
}, { root: null, threshold: 0.12 });

// Blocks animate in the first time they appear; identical re-renders show instantly.
function reveal(node, key) {
  node.classList.add("rv");
  if (seenBlocks.has(key) || reduceMotion) node.classList.add("in");
  else { seenBlocks.add(key); io.observe(node); }
  return node;
}
function revealVisible() { panel.querySelectorAll(".rv:not(.in)").forEach((n) => { io.unobserve(n); io.observe(n); }); }

function panelEmpty() {
  return el("div", { class: "panel-empty" },
    svg("svg", { viewBox: "0 0 72 72", "aria-hidden": "true" },
      svg("circle", { cx: 36, cy: 36, r: 30 }), svg("path", { d: "M36 14v44M14 36h44M28 28l16 16" })),
    el("p", {}, "Your itinerary will unfold here as the planner works."));
}

function renderPanel({ trip, issues = [], cost }) {
  if (!trip) return;
  $("#topbar-title").textContent = trip.title || "Untitled trip";
  const dates = trip.start_date
    ? `${fmtDate(trip.start_date, { month: "short", day: "numeric" })} – ${fmtDate(trip.end_date, { month: "short", day: "numeric", year: "numeric" }) || "?"}`
    : "Dates not set";
  const parts = [
    reveal(el("div", {},
      el("h2", { class: "p-title" }, trip.title || "Untitled trip"),
      el("div", { class: "pills" },
        el("span", { class: "pill date" }, dates),
        el("span", { class: "pill" }, `${trip.travelers} traveler${trip.travelers > 1 ? "s" : ""}`),
        el("span", { class: "pill" }, `${trip.pace} pace`),
        el("span", { class: "pill" }, trip.tier),
        (trip.prefs || []).slice(0, 4).map((p) => el("span", { class: "pill" }, p)))), "head:" + trip.title),
  ];

  if (cost && cost.total) parts.push(reveal(budgetCard(cost), "budget:" + cost.total + ":" + cost.budget));

  if (trip.flight) parts.push(el("div", { class: "section-h" }, "Flight"), reveal(boardingPass(trip.flight, trip.travelers), "flight:" + trip.flight.id));

  if (trip.hotel) parts.push(el("div", { class: "section-h" }, "Stay"), reveal(hotelCard(trip.hotel), "hotel:" + trip.hotel.id));

  if (issues.length) {
    parts.push(el("div", { class: "section-h" }, `Heads up · ${issues.length}`));
    for (const i of [...issues.filter((x) => x.severity === "error"), ...issues.filter((x) => x.severity !== "error")]) {
      const msg = i.date ? el("a", { href: "#" + tripId, onclick: (e) => jumpToDay(e, i.date) }, i.message) : i.message;
      parts.push(el("div", { class: "issue " + i.severity }, el("b", {}, i.severity === "error" ? "FIX" : "NOTE"), el("span", {}, msg)));
    }
  }

  if (trip.days?.length) {
    parts.push(el("div", { class: "section-h" }, `${trip.days.length} day${trip.days.length > 1 ? "s" : ""}`));
    trip.days.forEach((d, n) => parts.push(dayCard(d, n)));
  }

  if (parts.length === 1) parts.push(panelEmpty());
  const top = panel.scrollTop;
  panel.replaceChildren(...parts);
  panel.scrollTop = top;
  // Route lengths can only be measured once the SVG is in the document.
  panel.querySelectorAll(".sketch .route").forEach((p) => p.style.setProperty("--len", Math.ceil(p.getTotalLength())));
}

function budgetCard(cost) {
  const { total = 0, budget } = cost;
  const over = budget != null && total > budget;
  const frac = budget ? Math.min(1, total / budget) : 1;
  const C = 2 * Math.PI * 40;
  const fill = svg("circle", { class: "fill", cx: 48, cy: 48, r: 40, "stroke-dasharray": C, "stroke-dashoffset": C });
  // Start empty, then sweep to the real value on the next frame.
  requestAnimationFrame(() => requestAnimationFrame(() => fill.setAttribute("stroke-dashoffset", C * (1 - frac))));
  const seg = (cls, v) => el("span", { class: cls, style: `flex-grow:${v || 0}` });
  return el("div", { class: "card budget" + (over ? " over" : "") },
    svg("svg", { class: "ring", viewBox: "0 0 96 96", role: "img",
      "aria-label": budget ? `${Math.round((total / budget) * 100)}% of budget used` : "Estimated total" },
      svg("circle", { class: "track", cx: 48, cy: 48, r: 40 }), fill),
    el("div", {},
      el("div", { class: "figure" }, usd(total)),
      el("div", { class: "of" }, budget != null
        ? (over ? `${usd(total - budget)} over the ${usd(budget)} budget` : `of ${usd(budget)} · ${usd(budget - total)} left`)
        : "estimated · no budget set"),
      el("div", { class: "split", "aria-hidden": "true" }, seg("f", cost.flight), seg("h", cost.hotel), seg("a", cost.activities)),
      el("div", { class: "legend" },
        el("span", {}, el("i", { style: "background:var(--stamp)" }), `Flight ${usd(cost.flight)}`),
        el("span", {}, el("i", { style: "background:var(--sun)" }), `Stay ${usd(cost.hotel)}`),
        el("span", {}, el("i", { style: "background:var(--sea)" }), `Do ${usd(cost.activities)}`))));
}

function boardingPass(f, travelers) {
  const dur = f.duration_min ? `${Math.floor(f.duration_min / 60)}h ${pad2(f.duration_min % 60)}m` : "";
  return el("div", { class: "pass", role: "group", "aria-label": `Flight ${f.origin} to ${f.destination}` },
    el("div", { class: "pass-main" },
      el("div", { class: "pass-top" }, el("span", {}, f.airline), el("span", {}, f.stops ? `${f.stops} stop${f.stops > 1 ? "s" : ""}` : "Nonstop")),
      el("div", { class: "pass-route" },
        el("span", { class: "iata" }, f.origin),
        el("span", { class: "path" }, icon(ICONS.plane)),
        el("span", { class: "iata" }, f.destination)),
      el("div", { class: "pass-times" },
        el("span", {}, passTime(f.depart_at)),
        el("span", { class: "dur" }, dur),
        el("span", {}, passTime(f.arrive_at))),
      f.return_date && el("div", { class: "pass-times muted", style: "margin-top:6px" }, `Return ${fmtDate(f.return_date)}`)),
    el("div", { class: "pass-stub" },
      el("div", {}, el("div", { class: "price" }, usd(f.price_usd)),
        el("div", { class: "muted", style: "font-size:11px" }, `${travelers} pax`)),
      el("div", { class: "barcode", "aria-hidden": "true" }),
      link("Book", f.booking_url, "book")));
}

function hotelCard(h) {
  const nights = Math.max(1, Math.round((new Date(h.check_out) - new Date(h.check_in)) / 864e5));
  return el("div", { class: "card hotel" },
    el("div", { class: "hotel-icon" }, icon(ICONS.bed)),
    el("div", {},
      el("h4", {}, h.name),
      el("div", {},
        h.stars && el("span", { class: "stars", "aria-label": `${h.stars} stars` }, "★".repeat(h.stars)),
        h.rating && el("span", { class: "muted" }, ` ${h.rating}/5 guest rating`)),
      el("div", { class: "muted", style: "font-size:13px" }, `${fmtDate(h.check_in)} → ${fmtDate(h.check_out)} · ${nights} night${nights > 1 ? "s" : ""}`),
      el("div", { class: "hotel-row" },
        el("span", {}, `${usd(h.price_per_night_usd)}/night`),
        el("strong", {}, usd(h.total_usd) + " total"),
        link("Book", h.booking_url, "book"))));
}

const MODE = { walk: "🚶 walk", transit: "🚇 transit", drive: "🚗 drive" };

// Hand-drawn-ish route through the day's stops, projected from lat/lng.
function routeSketch(stops) {
  const pts = stops.filter((s) => s.place.lat != null && s.place.lng != null);
  if (pts.length < 2) return null;
  const W = 320, H = 120, P = 18;
  const lats = pts.map((s) => s.place.lat), lngs = pts.map((s) => s.place.lng);
  const midLat = (Math.min(...lats) + Math.max(...lats)) / 2;
  const kx = Math.cos((midLat * Math.PI) / 180);  // shrink longitude away from the equator
  const xs = lngs.map((l) => l * kx), ys = lats.map((l) => -l);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const scale = Math.min((W - 2 * P) / (x1 - x0 || 1e-9), (H - 2 * P) / (y1 - y0 || 1e-9));
  const ox = (W - (x1 - x0) * scale) / 2, oy = (H - (y1 - y0) * scale) / 2;
  const xy = pts.map((_, i) => [ox + (xs[i] - x0) * scale, oy + (ys[i] - y0) * scale]);
  // Catmull-Rom → cubic Bézier: a soft hand-drawn line that still passes through every stop.
  let d = `M${xy[0][0]},${xy[0][1]}`;
  for (let i = 0; i < xy.length - 1; i++) {
    const [p0, p1, p2, p3] = [xy[i - 1] || xy[i], xy[i], xy[i + 1], xy[i + 2] || xy[i + 1]];
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += ` C${c1} ${c2} ${p2}`;
  }
  const grid = [];
  for (let gx = 20; gx < W; gx += 20) grid.push(svg("line", { class: "grid", x1: gx, y1: 0, x2: gx, y2: H }));
  for (let gy = 20; gy < H; gy += 20) grid.push(svg("line", { class: "grid", x1: 0, y1: gy, x2: W, y2: gy }));
  return svg("svg", { class: "sketch", viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "xMidYMid meet", role: "img",
    "aria-label": `Route: ${pts.map((s) => s.place.name).join(" → ")}` },
    grid,
    svg("path", { class: "route", d }),
    xy.map(([x, y], i) => svg("g", { style: `--i:${i}` },
      svg("circle", { class: "pin", cx: x, cy: y, r: 8, style: `--i:${i}` }),
      svg("text", { x, y, style: `--i:${i}` }, String(i + 1)))));
}

function dayCard(day, n) {
  const key = "day:" + day.date + ":" + day.stops.map((s) => s.id).join(",");
  return reveal(el("article", { class: "card day", id: "day-" + day.date },
    el("div", { class: "day-head" },
      el("div", { class: "day-num" }, pad2(n + 1)),
      el("div", {},
        el("div", { class: "day-date" }, fmtDate(day.date, { weekday: "long", month: "short", day: "numeric" })),
        el("div", { class: "day-area" }, day.area || `Day ${n + 1}`))),
    day.notes && el("p", { class: "day-notes" }, day.notes),
    routeSketch(day.stops),
    el("ol", { class: "stops" }, day.stops.map((s) => {
      const p = s.place;
      return el("li", { class: "stop" },
        s.travel_from_prev_min != null &&
          el("div", { class: "leg" }, `${MODE[s.travel_mode] || "→"} · ${s.travel_from_prev_min} min`),
        el("div", { class: "body" },
          el("span", { class: "stop-time" }, hhmm(s.start)),
          el("span", { class: "stop-dot", "aria-hidden": "true" }),
          el("div", { class: "stop-name" }, link(p.name, p.maps_url)),
          el("div", { class: "stop-meta" },
            el("span", {}, `${s.duration_min} min`),
            s.est_cost_usd != null && el("span", {}, s.est_cost_usd ? `~${usd(s.est_cost_usd)}` : "free"),
            p.rating && el("span", { class: "rating" }, `★ ${p.rating}`)),
          s.note && el("div", { class: "stop-note" }, s.note)));
    }))), key);
}

function jumpToDay(e, date) {
  e.preventDefault();
  if (document.body.dataset.view !== "panel" && matchMedia("(max-width: 1180px)").matches) {
    document.body.dataset.view = "panel";
    syncViewToggle();
  }
  const target = document.getElementById("day-" + date);
  target?.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
  target?.animate?.([{ boxShadow: "0 0 0 3px var(--stamp)" }, { boxShadow: "0 0 0 0 transparent" }], { duration: 1400, easing: "ease-out" });
}

renderPostcards();
openTrip();
