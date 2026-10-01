"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import { ArrowLeft, ArrowRight, CalendarDays, Map, MessageCircle, Plane, Trash2 } from "lucide-react";
import clsx from "clsx";
import { Photo } from "@/components/Photo";
import { Logo } from "@/components/Header";
import { deleteTrip, listTrips } from "@/lib/api";
import { destinationImage } from "@/lib/images";
import { dateRange } from "@/lib/format";
import type { TripSummary } from "@/lib/types";

const inView = (i = 0) => ({
  initial: { opacity: 0, y: 32 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-60px" },
  transition: { duration: 0.8, delay: i * 0.08, ease: [0.16, 1, 0.3, 1] as const },
});

function SectionHead({ kicker, title, children }: { kicker: string; title: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-6">
      <motion.div {...inView()}>
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-coral">{kicker}</p>
        <h2 className="mt-3 max-w-2xl font-display text-5xl leading-[1] tracking-tight sm:text-6xl">{title}</h2>
      </motion.div>
      {children}
    </div>
  );
}

// ── Destinations ────────────────────────────────────────────────────────────

// Aligns the carousel's first card with the max-w-7xl content column, edge-to-edge scroll beyond it.
const GUTTER = "max(1rem, calc((100vw - 80rem) / 2 + 1.5rem))";

const DESTINATIONS = [
  { name: "Lisbon", country: "Portugal", tag: "Food & viewpoints", days: 5, prompt: "5 days in Lisbon in May for 2 people, ~$3000. We love food markets, viewpoints and walking." },
  { name: "Kyoto", country: "Japan", tag: "Temples & gardens", days: 6, prompt: "A relaxed 6 days in Kyoto in April for 2, temples, gardens and tea houses, mid budget." },
  { name: "Mexico City", country: "Mexico", tag: "Tacos & museums", days: 4, prompt: "Long weekend in Mexico City for a food-obsessed couple: street food, markets and museums." },
  { name: "Reykjavik", country: "Iceland", tag: "Hot springs & hikes", days: 6, prompt: "6 days around Reykjavik in September for 2 people, hot springs and day hikes, ~$4000." },
  { name: "Marrakech", country: "Morocco", tag: "Souks & riads", days: 4, prompt: "4 days in Marrakech staying in a riad, souks, gardens and a day trip to the Atlas, mid budget." },
  { name: "Cape Town", country: "South Africa", tag: "Coast & wine", days: 7, prompt: "A week in Cape Town for 2 in November: coastline, Table Mountain and a wine day, ~$5000." },
];

export function Destinations({ onStart }: { onStart: (prompt: string) => void }) {
  const track = useRef<HTMLDivElement>(null);
  const scroll = (dir: number) => track.current?.scrollBy({ left: dir * track.current.clientWidth * 0.8, behavior: "smooth" });

  return (
    <section id="destinations" className="scroll-mt-20 py-24 sm:py-32">
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <SectionHead kicker="Start somewhere" title={<>Trips people are <em>dreaming</em> about</>}>
          <div className="flex gap-2">
            <button aria-label="Previous" onClick={() => scroll(-1)} className="grid size-12 place-items-center rounded-full border border-line bg-white transition hover:border-ink"><ArrowLeft className="size-5" /></button>
            <button aria-label="Next" onClick={() => scroll(1)} className="grid size-12 place-items-center rounded-full border border-line bg-white transition hover:border-ink"><ArrowRight className="size-5" /></button>
          </div>
        </SectionHead>
      </div>
      <div ref={track} className="mt-12 flex snap-x snap-mandatory gap-5 overflow-x-auto scroll-smooth pb-6 [scrollbar-width:none]"
        style={{ paddingInline: GUTTER, scrollPaddingInline: GUTTER }}>
        {DESTINATIONS.map((d, i) => (
          <motion.button key={d.name} {...inView(i)} onClick={() => onStart(d.prompt)}
            className="group relative w-[78vw] shrink-0 snap-start overflow-hidden rounded-[28px] text-left shadow-card sm:w-[340px]">
            <Photo src={destinationImage(d.name)} label={d.name} className="aspect-[3/4] w-full transition-transform duration-700 ease-[cubic-bezier(.16,1,.3,1)] group-hover:scale-105" />
            <div className="absolute inset-0 bg-gradient-to-t from-ink/80 via-ink/10 to-transparent" />
            <span className="absolute left-4 top-4 rounded-full bg-white/90 px-3 py-1 text-xs font-semibold text-ink backdrop-blur">{d.tag}</span>
            <div className="absolute inset-x-0 bottom-0 p-6 text-white">
              <p className="text-sm text-white/75">{d.country} · {d.days} days</p>
              <h3 className="mt-1 font-display text-4xl leading-none">{d.name}</h3>
              <span className="mt-4 inline-flex translate-y-2 items-center gap-1.5 rounded-full bg-coral px-4 py-2 text-sm font-semibold opacity-0 transition-all duration-500 group-hover:translate-y-0 group-hover:opacity-100 group-focus-visible:translate-y-0 group-focus-visible:opacity-100">
                Plan this trip <ArrowRight className="size-4" />
              </span>
            </div>
          </motion.button>
        ))}
      </div>
    </section>
  );
}

// ── How it works ────────────────────────────────────────────────────────────

const STEPS = [
  { icon: MessageCircle, title: "Say it like you'd text a friend", body: "Where, when, who's coming and a rough budget. Ask for changes the same way." },
  { icon: Plane, title: "It searches the real thing", body: "Live flights and hotels, places with opening hours, and travel times between every stop." },
  { icon: Map, title: "See your days on a map", body: "Each day is clustered by neighborhood so you're not zig-zagging across town. Approve and book." },
];

export function HowItWorks() {
  return (
    <section id="how" className="scroll-mt-20 bg-ink py-24 text-white sm:py-32">
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <motion.div {...inView()}>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-coral">How it works</p>
          <h2 className="mt-3 max-w-3xl font-display text-5xl leading-[1] tracking-tight sm:text-6xl">From a sentence to a plan you can <em className="text-[#ffd9c9]">actually</em> follow</h2>
        </motion.div>
        <div className="mt-16 grid gap-6 md:grid-cols-3">
          {STEPS.map((s, i) => (
            <motion.div key={s.title} {...inView(i + 1)} className="group rounded-[28px] border border-white/10 bg-white/[0.04] p-8 transition hover:bg-white/[0.07]">
              <div className="flex items-center justify-between">
                <span className="grid size-14 place-items-center rounded-2xl bg-coral/15 text-coral transition-transform duration-500 group-hover:-rotate-6 group-hover:scale-110"><s.icon className="size-7" /></span>
                <span className="font-display text-6xl text-white/15">0{i + 1}</span>
              </div>
              <h3 className="mt-8 text-xl font-semibold">{s.title}</h3>
              <p className="mt-2 text-white/65">{s.body}</p>
              <StepPreview i={i} />
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

// Small animated vignettes so each step shows rather than tells.
function StepPreview({ i }: { i: number }) {
  if (i === 0)
    return (
      <div className="mt-8 space-y-2 text-sm">
        <motion.div initial={{ opacity: 0, x: 20 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ delay: 0.4 }}
          className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-white px-4 py-2.5 text-ink">4 days in Rome, pasta + ruins 🍝</motion.div>
        <motion.div initial={{ opacity: 0, x: -20 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ delay: 0.9 }}
          className="w-fit max-w-[85%] rounded-2xl rounded-bl-md bg-white/10 px-4 py-2.5">On it. Checking flights from your city…</motion.div>
      </div>
    );
  if (i === 1)
    return (
      <ul className="mt-8 space-y-2 font-mono text-[13px] text-white/70">
        {["Flights FCO · 14 options", "Hotels in Monti · 9 options", "Colosseum · open 9–19"].map((t, k) => (
          <motion.li key={t} initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: true }} transition={{ delay: 0.4 + k * 0.35 }} className="flex items-center gap-2">
            <span className="grid size-4 place-items-center rounded-full bg-lagoon text-[10px] text-white">✓</span>{t}
          </motion.li>
        ))}
      </ul>
    );
  return (
    <svg viewBox="0 0 240 90" className="mt-6 w-full" aria-hidden>
      <motion.path d="M12 70 C 60 10, 110 90, 150 40 S 220 30, 228 20" fill="none" stroke="#ff5b3a" strokeWidth="2.5" strokeLinecap="round" strokeDasharray="1 0"
        initial={{ pathLength: 0 }} whileInView={{ pathLength: 1 }} viewport={{ once: true }} transition={{ duration: 1.8, delay: 0.4, ease: "easeInOut" }} />
      {[[12, 70], [100, 52], [150, 40], [228, 20]].map(([x, y], k) => (
        <motion.circle key={k} cx={x} cy={y} r="6" fill="#0e1a24" stroke="white" strokeWidth="2.5"
          initial={{ scale: 0 }} whileInView={{ scale: 1 }} viewport={{ once: true }} transition={{ delay: 0.5 + k * 0.4, type: "spring" }} />
      ))}
    </svg>
  );
}

// ── Your trips ──────────────────────────────────────────────────────────────

export function YourTrips() {
  const [trips, setTrips] = useState<TripSummary[] | null>(null);
  const [arming, setArming] = useState<string | null>(null);
  useEffect(() => { listTrips().then(setTrips).catch(() => setTrips([])); }, []);
  if (!trips?.length) return null;

  async function remove(id: string) {
    if (arming !== id) { setArming(id); setTimeout(() => setArming((a) => (a === id ? null : a)), 3000); return; }
    await deleteTrip(id).catch(() => {});
    setTrips((t) => t?.filter((x) => x.id !== id) ?? null);
  }

  return (
    <section id="trips" className="scroll-mt-20 py-24 sm:py-32">
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <SectionHead kicker="Your journeys" title="Pick up where you left off" />
        <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {trips.slice(0, 9).map((t, i) => (
            <motion.div key={t.id} {...inView(i)} className="group relative overflow-hidden rounded-[24px] bg-white shadow-card transition-shadow hover:shadow-lift">
              <Link href={`/plan?id=${t.id}`} className="block">
                <Photo src={destinationImage(t.destination)} label={t.destination || t.title} className="aspect-[16/10]">
                  <div className="absolute inset-0 bg-gradient-to-t from-ink/50 to-transparent" />
                  <StatusBadge status={t.status} />
                </Photo>
                <div className="p-5">
                  <h3 className="truncate font-display text-2xl">{t.title || "Untitled trip"}</h3>
                  <p className="mt-1 flex items-center gap-1.5 text-sm text-ink-soft">
                    <CalendarDays className="size-4" /> {dateRange(t.start_date, t.end_date)}{t.days ? ` · ${t.days} days planned` : ""}
                  </p>
                </div>
              </Link>
              <button onClick={() => remove(t.id)} aria-label={arming === t.id ? "Confirm delete" : `Delete ${t.title || "trip"}`}
                className={clsx("absolute right-3 top-3 flex items-center gap-1.5 rounded-full px-3 py-2 text-xs font-semibold backdrop-blur transition",
                  arming === t.id ? "bg-coral text-white" : "bg-white/85 text-ink opacity-0 group-hover:opacity-100 focus-visible:opacity-100")}>
                <Trash2 className="size-3.5" />{arming === t.id && "Delete?"}
              </button>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

export function StatusBadge({ status }: { status: TripSummary["status"] }) {
  const styles = { planning: "bg-white/90 text-ink", awaiting_approval: "bg-gold text-ink", approved: "bg-lagoon text-white" }[status];
  return <span className={clsx("absolute bottom-3 left-3 rounded-full px-3 py-1 text-xs font-semibold capitalize", styles)}>{status.replace("_", " ")}</span>;
}

// ── Footer ──────────────────────────────────────────────────────────────────

export function Footer({ onStart }: { onStart: () => void }) {
  return (
    <footer className="border-t border-line bg-white">
      <div className="mx-auto max-w-7xl px-4 py-20 sm:px-6">
        <motion.div {...inView()} className="flex flex-wrap items-end justify-between gap-8">
          <h2 className="max-w-xl font-display text-5xl leading-none tracking-tight sm:text-6xl">Your next trip is one sentence away.</h2>
          <button onClick={onStart} className="group flex items-center gap-2 rounded-full bg-coral px-7 py-4 text-lg font-semibold text-white transition hover:bg-coral-deep">
            Start planning <ArrowRight className="size-5 transition-transform group-hover:translate-x-1" />
          </button>
        </motion.div>
        <div className="mt-16 flex flex-wrap items-center justify-between gap-4 border-t border-line pt-8 text-sm text-ink-soft">
          <Logo />
          <p>Prices, hours and travel times come from live search. Always confirm before you book.</p>
        </div>
      </div>
    </footer>
  );
}
