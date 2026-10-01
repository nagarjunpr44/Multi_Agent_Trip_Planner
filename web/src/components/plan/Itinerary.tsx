"use client";

import { createElement, useEffect, useRef } from "react";
import { motion } from "motion/react";
import {
  AlertTriangle, ArrowUpRight, BedDouble, Bike, Building2, Car, Coffee, Footprints, Landmark, MapPin, Mountain,
  Plane, ShoppingBag, Star, TrainFront, Trees, Users, Utensils, Wine,
} from "lucide-react";
import clsx from "clsx";
import { Photo } from "@/components/Photo";
import { destinationImage } from "@/lib/images";
import { dateRange, fmtClock, fmtDate, fmtDuration, hhmm, nights, safeUrl, usd } from "@/lib/format";
import type { Cost, Day, Flight, Hotel, Issue, Stop } from "@/lib/types";
import type { TripState } from "./useTrip";

export const DAY_COLORS = ["#ff5b3a", "#0f766e", "#e9a23b", "#6d5bd0", "#2f7dd1", "#d14d8b", "#3b8f4a"];

const inView = (i = 0) => ({
  initial: { opacity: 0, y: 24 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-40px" },
  transition: { duration: 0.6, delay: Math.min(i, 6) * 0.05, ease: [0.16, 1, 0.3, 1] as const },
});

export function Itinerary({ state, busy, activeDay, onActiveDay, hoverStop, onHoverStop, onReview, className }: {
  state: TripState | null;
  busy: boolean;
  activeDay: number;
  onActiveDay: (i: number) => void;
  hoverStop: string | null;
  onHoverStop: (id: string | null) => void;
  onReview: () => void;
  className?: string;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  const trip = state?.trip;
  const days = trip?.days ?? [];

  // Scrollspy: the day nearest the top of the pane becomes active (drives the map).
  useEffect(() => {
    const root = scroller.current;
    if (!root || !days.length) return;
    const io = new IntersectionObserver(
      (entries) => {
        const hit = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (hit) onActiveDay(Number((hit.target as HTMLElement).dataset.day));
      },
      { root, rootMargin: "-120px 0px -55% 0px" },
    );
    root.querySelectorAll("[data-day]").forEach((n) => io.observe(n));
    return () => io.disconnect();
  }, [days.length, onActiveDay]);

  const jump = (i: number) => {
    onActiveDay(i);
    scroller.current?.querySelector(`[data-day="${i}"]`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  if (!trip) return <section className={clsx("min-h-0 flex-col bg-sand", className)}><Skeleton /></section>;

  const destination = trip.destinations[0] || "";
  return (
    <section aria-label="Itinerary" className={clsx("min-h-0 flex-col bg-sand", className)}>
      <div ref={scroller} className="pane @container relative min-h-0 flex-1 overflow-y-auto">
        {/* Cover */}
        <Photo src={destinationImage(destination)} label={destination || trip.title || "trip"} priority className="h-64 sm:h-72">
          <div className="absolute inset-0 bg-gradient-to-t from-ink/85 via-ink/25 to-ink/10" />
          <div className="absolute inset-x-0 bottom-0 px-6 pb-16 text-white">
            <motion.p key={trip.status} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mb-2 inline-block rounded-full bg-white/20 px-3 py-1 text-xs font-semibold capitalize backdrop-blur">
              {trip.status.replace("_", " ")}
            </motion.p>
            <h1 className="font-display text-5xl leading-none tracking-tight">{trip.title || (busy ? "Planning your trip…" : "New trip")}</h1>
            <p className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm text-white/85">
              <span>{dateRange(trip.start_date, trip.end_date)}</span>
              <span className="flex items-center gap-1"><Users className="size-3.5" />{trip.travelers} traveler{trip.travelers > 1 ? "s" : ""}</span>
              <span className="capitalize">{trip.pace} pace · {trip.tier}</span>
            </p>
          </div>
        </Photo>

        <div className="relative -mt-10 space-y-8 px-4 pb-24 sm:px-6">
          {/* At a glance */}
          <div className={clsx("grid gap-3", trip.flight ? "@lg:grid-cols-2 @5xl:grid-cols-[1fr_1.4fr_1fr]" : "@lg:grid-cols-3")}>
            <BudgetCard cost={state!.cost} />
            <FlightCard flight={trip.flight} travelers={trip.travelers} />
            <HotelCard hotel={trip.hotel} />
          </div>

          {trip.status === "awaiting_approval" && (
            <motion.button {...inView()} onClick={onReview}
              className="flex w-full items-center gap-3 rounded-2xl bg-ink px-5 py-4 text-left text-white shadow-lift transition hover:bg-ink/90">
              <span className="grid size-10 place-items-center rounded-full bg-coral"><Star className="size-5" /></span>
              <span className="flex-1"><span className="block font-semibold">Plan ready for your review</span><span className="text-sm text-white/70">Approve it or ask for changes in the chat</span></span>
              <ArrowUpRight className="size-5" />
            </motion.button>
          )}

          <Issues issues={state!.issues} onJump={(date) => jump(days.findIndex((d) => d.date === date))} />

          {days.length > 0 ? (
            <div>
              <nav aria-label="Days" className="sticky top-0 z-10 -mx-4 flex gap-2 overflow-x-auto border-b border-line bg-sand/90 px-4 py-3 backdrop-blur-md [scrollbar-width:none] sm:-mx-6 sm:px-6">
                {days.map((d, i) => (
                  <button key={d.date} onClick={() => jump(i)} aria-current={i === activeDay}
                    className={clsx("relative shrink-0 rounded-full px-4 py-2 text-sm font-semibold transition", i === activeDay ? "text-white" : "bg-white text-ink-soft hover:text-ink")}>
                    {i === activeDay && <motion.span layoutId="day-pill" className="absolute inset-0 rounded-full" style={{ background: DAY_COLORS[i % DAY_COLORS.length] }} transition={{ type: "spring", bounce: 0.2, duration: 0.5 }} />}
                    <span className="relative">Day {i + 1} <span className="font-normal opacity-75">· {fmtDate(d.date, { weekday: "short", day: "numeric" })}</span></span>
                  </button>
                ))}
              </nav>
              <div className="mt-6 space-y-12">
                {days.map((d, i) => <DaySection key={d.date} day={d} index={i} hoverStop={hoverStop} onHoverStop={onHoverStop} />)}
              </div>
            </div>
          ) : (
            <EmptyDays busy={busy} />
          )}
        </div>
      </div>
    </section>
  );
}

// ── At a glance ─────────────────────────────────────────────────────────────

const glance = "rounded-2xl bg-white p-4 shadow-card";

function BudgetCard({ cost }: { cost: Cost }) {
  const { total, budget } = cost;
  const frac = budget ? Math.min(1, total / budget) : total ? 1 : 0;
  const over = budget != null && total > budget;
  const C = 2 * Math.PI * 22;
  return (
    <motion.div {...inView(0)} className={clsx(glance, "flex items-center gap-4")}>
      <svg viewBox="0 0 52 52" className="size-14 -rotate-90" role="img" aria-label={budget ? `${Math.round((total / budget) * 100)}% of budget` : "Estimated total"}>
        <circle cx="26" cy="26" r="22" fill="none" strokeWidth="6" className="stroke-sand-2" />
        <motion.circle cx="26" cy="26" r="22" fill="none" strokeWidth="6" strokeLinecap="round" stroke={over ? "#e2411f" : "#0f766e"}
          strokeDasharray={C} initial={{ strokeDashoffset: C }} animate={{ strokeDashoffset: C * (1 - frac) }} transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1] }} />
      </svg>
      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">Budget</p>
        <p className="font-display text-3xl leading-tight">{usd(total)}</p>
        <p className={clsx("text-xs", over ? "font-semibold text-coral-deep" : "text-ink-soft")}>
          {budget == null ? "No budget set" : over ? `${usd(total - budget)} over ${usd(budget)}` : `${usd(budget - total)} left of ${usd(budget)}`}
        </p>
      </div>
    </motion.div>
  );
}

function FlightCard({ flight: f, travelers }: { flight?: Flight | null; travelers: number }) {
  if (!f) return <Pending icon={Plane} label="Flight" text="Not chosen yet" i={1} />;
  return (
    <motion.div {...inView(1)} className={clsx(glance, "@lg:-order-1 @lg:col-span-2 @5xl:order-none @5xl:col-span-1")}>
      <div className="flex items-center justify-between gap-2 text-xs font-semibold uppercase tracking-wider text-ink-soft">
        <span className="flex min-w-0 items-center gap-1.5"><Plane className="size-3.5 shrink-0" /><span className="truncate">{f.airline}</span></span>
        <span className="shrink-0">{f.stops ? `${f.stops} stop${f.stops > 1 ? "s" : ""}` : "Nonstop"}</span>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <div><p className="font-display text-3xl leading-none">{f.origin}</p><p className="mt-1 text-xs text-ink-soft">{fmtClock(f.depart_at)}</p></div>
        <div className="relative mx-1 h-px flex-1 border-t border-dashed border-ink-soft/40">
          <motion.span className="absolute -top-2 text-coral" initial={{ left: "0%" }} animate={{ left: ["0%", "85%", "0%"] }} transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}>
            <Plane className="size-4" />
          </motion.span>
        </div>
        <div className="text-right"><p className="font-display text-3xl leading-none">{f.destination}</p><p className="mt-1 text-xs text-ink-soft">{fmtClock(f.arrive_at)}</p></div>
      </div>
      <div className="mt-2 flex items-center justify-between text-xs">
        <span className="text-ink-soft">{fmtDate(f.depart_at)}{f.duration_min ? ` · ${fmtDuration(f.duration_min)}` : ""}</span>
        <span className="font-semibold">{usd(f.price_usd)} <span className="font-normal text-ink-soft">· {travelers} pax</span></span>
      </div>
      <BookLink url={f.booking_url} />
    </motion.div>
  );
}

function HotelCard({ hotel: h }: { hotel?: Hotel | null }) {
  if (!h) return <Pending icon={BedDouble} label="Stay" text="Not chosen yet" i={2} />;
  const n = nights(h.check_in, h.check_out);
  return (
    <motion.div {...inView(2)} className={glance}>
      <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-ink-soft"><BedDouble className="size-3.5" />Stay · {n} night{n > 1 ? "s" : ""}</p>
      <p className="mt-1.5 truncate font-display text-2xl leading-tight">{h.name}</p>
      <p className="mt-1 flex items-center gap-1 text-xs text-ink-soft">
        {h.stars ? <span className="text-gold">{"★".repeat(h.stars)}</span> : null}
        {h.rating ? <span>{h.rating}/5</span> : null}
      </p>
      <div className="mt-2 flex items-center justify-between text-xs">
        <span className="text-ink-soft">{usd(h.price_per_night_usd)}/night</span>
        <span className="font-semibold">{usd(h.total_usd)} total</span>
      </div>
      <BookLink url={h.booking_url} />
    </motion.div>
  );
}

function Pending({ icon: Icon, label, text, i }: { icon: typeof Plane; label: string; text: string; i: number }) {
  return (
    <motion.div {...inView(i)} className={clsx(glance, "flex items-center gap-3 border border-dashed border-line")}>
      <span className="grid size-11 place-items-center rounded-xl bg-sand text-ink-soft"><Icon className="size-5" /></span>
      <div><p className="text-xs font-semibold uppercase tracking-wider text-ink-soft">{label}</p><p className="text-sm text-ink-soft">{text}</p></div>
    </motion.div>
  );
}

function BookLink({ url }: { url?: string }) {
  const href = safeUrl(url);
  if (!href) return null;
  return (
    <a href={href} target="_blank" rel="noopener" className="group mt-3 flex items-center justify-center gap-1 rounded-xl bg-sand py-2 text-xs font-semibold transition hover:bg-ink hover:text-white">
      Book <ArrowUpRight className="size-3.5 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
    </a>
  );
}

function Issues({ issues, onJump }: { issues: Issue[]; onJump: (date: string) => void }) {
  if (!issues.length) return null;
  const sorted = [...issues.filter((i) => i.severity === "error"), ...issues.filter((i) => i.severity !== "error")];
  return (
    <motion.div {...inView()} className="rounded-2xl border border-gold/40 bg-gold/10 p-4">
      <p className="flex items-center gap-2 text-sm font-semibold"><AlertTriangle className="size-4 text-gold" />Heads up · {issues.length}</p>
      <ul className="mt-2 space-y-1.5 text-sm">
        {sorted.map((i, k) => (
          <li key={k} className={clsx("flex gap-2", i.severity === "error" && "text-coral-deep")}>
            <span className="mt-2 size-1.5 shrink-0 rounded-full bg-current" />
            {i.date ? <button onClick={() => onJump(i.date!)} className="text-left underline-offset-2 hover:underline">{i.message}</button> : i.message}
          </li>
        ))}
      </ul>
    </motion.div>
  );
}

// ── Days ────────────────────────────────────────────────────────────────────

const MODE = { walk: { icon: Footprints, label: "walk" }, transit: { icon: TrainFront, label: "transit" }, drive: { icon: Car, label: "drive" } };

// Map Google place types to an icon for the photo placeholder.
function placeIcon(types: string[] = []) {
  const has = (...k: string[]) => types.some((t) => k.some((x) => t.includes(x)));
  if (has("restaurant", "food", "meal")) return Utensils;
  if (has("cafe", "bakery")) return Coffee;
  if (has("bar", "night_club", "winery")) return Wine;
  if (has("museum", "art_gallery", "church", "place_of_worship", "tourist_attraction")) return Landmark;
  if (has("park", "garden", "zoo")) return Trees;
  if (has("natural_feature", "hiking", "beach")) return Mountain;
  if (has("store", "market", "shopping")) return ShoppingBag;
  if (has("bicycle")) return Bike;
  if (has("lodging")) return Building2;
  return MapPin;
}
const PlaceIcon = ({ types, className }: { types?: string[]; className?: string }) => createElement(placeIcon(types), { className });

function DaySection({ day, index, hoverStop, onHoverStop }: { day: Day; index: number; hoverStop: string | null; onHoverStop: (id: string | null) => void }) {
  const color = DAY_COLORS[index % DAY_COLORS.length];
  const spend = day.stops.reduce((s, x) => s + (x.est_cost_usd ?? 0), 0);
  return (
    <section data-day={index} className="scroll-mt-20">
      <motion.header {...inView()} className="flex items-end gap-4">
        <span className="font-display text-6xl leading-[0.8]" style={{ color }}>{String(index + 1).padStart(2, "0")}</span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-soft">{fmtDate(day.date, { weekday: "long", month: "long", day: "numeric" })}</p>
          <h2 className="truncate font-display text-3xl leading-tight">{day.area || `Day ${index + 1}`}</h2>
        </div>
        <p className="hidden shrink-0 text-right text-xs text-ink-soft sm:block">{day.stops.length} stops<br />{spend ? `~${usd(spend)}` : ""}</p>
      </motion.header>
      {day.notes && <p className="mt-3 text-[15px] text-ink-soft">{day.notes}</p>}
      <ol className="mt-5">
        {day.stops.map((s, i) => (
          <li key={s.id}>
            {s.travel_from_prev_min != null && i > 0 && <Leg stop={s} color={color} />}
            <StopCard stop={s} n={i + 1} color={color} i={i} active={hoverStop === s.id} onHover={onHoverStop} />
          </li>
        ))}
      </ol>
    </section>
  );
}

function Leg({ stop, color }: { stop: Stop; color: string }) {
  const mode = stop.travel_mode ? MODE[stop.travel_mode] : null;
  const Icon = mode?.icon ?? Footprints;
  return (
    <div className="flex items-center gap-3 py-1.5 pl-[22px]">
      <span className="h-8 border-l-2 border-dotted" style={{ borderColor: color }} />
      <span className="flex items-center gap-1.5 rounded-full bg-white px-2.5 py-1 text-xs font-medium text-ink-soft shadow-card">
        <Icon className="size-3.5" />{stop.travel_from_prev_min} min {mode?.label ?? ""}
      </span>
    </div>
  );
}

function StopCard({ stop: s, n, color, i, active, onHover }: { stop: Stop; n: number; color: string; i: number; active: boolean; onHover: (id: string | null) => void }) {
  const p = s.place;
  const maps = safeUrl(p.maps_url);
  return (
    <motion.article {...inView(i)}
      onMouseEnter={() => onHover(s.id)} onMouseLeave={() => onHover(null)} onFocus={() => onHover(s.id)} onBlur={() => onHover(null)}
      className={clsx("group flex gap-4 rounded-2xl bg-white p-3 shadow-card ring-2 transition-[box-shadow,transform] duration-300 hover:-translate-y-0.5 hover:shadow-lift", active ? "ring-coral/60" : "ring-transparent")}>
      <div className="relative shrink-0">
        <Photo label={p.name} className="size-24 rounded-xl sm:size-28">
          <span className="absolute inset-0 grid place-items-center text-white/90"><PlaceIcon types={p.types} className="size-8 drop-shadow" /></span>
        </Photo>
        <span className="absolute -left-2 -top-2 grid size-7 place-items-center rounded-full border-2 border-white text-xs font-bold text-white shadow" style={{ background: color }}>{n}</span>
      </div>
      <div className="min-w-0 flex-1 py-0.5">
        <p className="text-xs font-semibold text-ink-soft">{hhmm(s.start)} · {fmtDuration(s.duration_min)}</p>
        <h3 className="mt-0.5 text-[17px] font-semibold leading-snug">
          {maps ? <a href={maps} target="_blank" rel="noopener" className="hover:text-coral">{p.name}</a> : p.name}
        </h3>
        <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-ink-soft">
          {p.rating ? <span className="flex items-center gap-0.5 font-semibold text-ink"><Star className="size-3 fill-gold text-gold" />{p.rating}{p.user_ratings ? <span className="font-normal text-ink-soft">({p.user_ratings.toLocaleString()})</span> : null}</span> : null}
          {s.est_cost_usd != null && <span>{s.est_cost_usd ? `~${usd(s.est_cost_usd)}` : "Free"}</span>}
          {p.address && <span className="truncate">{p.address.split(",")[0]}</span>}
        </p>
        {s.note && <p className="mt-2 line-clamp-3 text-sm leading-relaxed">{s.note}</p>}
      </div>
    </motion.article>
  );
}

function EmptyDays({ busy }: { busy: boolean }) {
  if (busy) return <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="h-28 animate-shimmer rounded-2xl bg-[linear-gradient(90deg,#ece5da,#f6f2ec,#ece5da)] bg-[length:200%_100%]" />)}</div>;
  return (
    <div className="rounded-3xl border border-dashed border-line px-6 py-14 text-center">
      <MapPin className="mx-auto size-8 text-ink-soft/60" />
      <p className="mt-3 font-display text-2xl">Your days will appear here</p>
      <p className="mt-1 text-sm text-ink-soft">Chat with the planner and watch the itinerary build itself.</p>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="animate-pulse">
      <div className="h-72 bg-sand-2" />
      <div className="-mt-10 grid gap-3 px-6 sm:grid-cols-3">{[0, 1, 2].map((i) => <div key={i} className="h-28 rounded-2xl bg-white" />)}</div>
      <div className="mt-8 space-y-3 px-6">{[0, 1, 2].map((i) => <div key={i} className="h-28 rounded-2xl bg-white/70" />)}</div>
    </div>
  );
}
