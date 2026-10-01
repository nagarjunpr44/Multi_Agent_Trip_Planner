"use client";

import { useEffect, useRef, useState } from "react";
import { motion, useScroll, useTransform } from "motion/react";
import { ArrowRight, Calendar, MapPin, Minus, Plus, Sparkles, Users, Wallet } from "lucide-react";
import clsx from "clsx";
import { Photo } from "@/components/Photo";
import { HERO_IMAGE } from "@/lib/images";

const IDEAS = [
  "5 days in Lisbon in May, 2 people, ~$3000, love food markets",
  "A slow week in Kyoto during cherry blossom season",
  "Long weekend in Mexico City for tacos and museums",
  "Family trip to Barcelona in July, beaches + Gaudí",
];

const rise = (i: number) => ({
  initial: { opacity: 0, y: 28 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.9, delay: 0.15 + i * 0.12, ease: [0.16, 1, 0.3, 1] as const },
});

export function Hero({ onStart, starting, error }: { onStart: (prompt: string) => void; starting: boolean; error: string | null }) {
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const y = useTransform(scrollYProgress, [0, 1], ["0%", "18%"]);
  const scale = useTransform(scrollYProgress, [0, 1], [1.05, 1.15]);

  return (
    <section ref={ref} className="relative isolate flex min-h-[92svh] items-end overflow-hidden pb-14 pt-32 sm:items-center sm:pb-24">
      <motion.div style={{ y, scale }} className="absolute inset-0 -z-10">
        <Photo src={HERO_IMAGE} label="hero" priority className="h-full w-full" />
      </motion.div>
      {/* Legibility scrim */}
      <div className="absolute inset-0 -z-10 bg-[linear-gradient(180deg,rgb(14_26_36/.55)_0%,rgb(14_26_36/.15)_40%,rgb(14_26_36/.65)_100%)]" />

      <div className="mx-auto w-full max-w-7xl px-4 sm:px-6">
        <motion.p {...rise(0)} className="mb-5 inline-flex items-center gap-2 rounded-full bg-white/15 px-3.5 py-1.5 text-sm font-medium text-white backdrop-blur-md">
          <Sparkles className="size-4 text-gold" /> Real prices, real opening hours, real walking times
        </motion.p>
        <motion.h1 {...rise(1)} className="max-w-4xl font-display text-[clamp(3rem,8vw,7.5rem)] leading-[0.92] tracking-[-0.02em] text-white">
          Plan less. <em className="text-[#ffd9c9]">Wander</em> more.
        </motion.h1>
        <motion.p {...rise(2)} className="mt-6 max-w-xl text-lg text-white/85">
          Tell Wayfarer where you&apos;re dreaming of. It searches flights, hotels and places, then builds a day-by-day plan you can see on a map.
        </motion.p>
        <motion.div {...rise(3)} className="mt-10">
          <PromptBar onStart={onStart} starting={starting} />
          {error && <p role="alert" className="mt-3 text-sm font-medium text-[#ffd9c9]">Couldn&apos;t start a trip: {error}</p>}
        </motion.div>
      </div>
    </section>
  );
}

function PromptBar({ onStart, starting }: { onStart: (prompt: string) => void; starting: boolean }) {
  const [mode, setMode] = useState<"guided" | "free">("guided");
  const [where, setWhere] = useState("");
  const [when, setWhen] = useState("");
  const [who, setWho] = useState(2);
  const [budget, setBudget] = useState("");
  const [free, setFree] = useState("");
  const [idea, setIdea] = useState(0);
  const whereRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const t = setInterval(() => setIdea((i) => (i + 1) % IDEAS.length), 3500);
    return () => clearInterval(t);
  }, []);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (starting) return;
    if (mode === "free") {
      if (free.trim()) onStart(free.trim());
      return;
    }
    if (!where.trim()) { whereRef.current?.focus(); return; }
    const parts = [`Plan a trip to ${where.trim()}`];
    if (when.trim()) parts.push(when.trim());
    parts.push(`${who} traveler${who > 1 ? "s" : ""}`);
    if (budget) parts.push(`budget around ${budget}`);
    onStart(parts.join(", ") + ".");
  }

  const field = "flex min-w-0 flex-1 flex-col gap-0.5 rounded-2xl px-5 py-3 transition hover:bg-sand focus-within:bg-sand";
  const label = "flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.12em] text-ink-soft";
  const input = "w-full bg-transparent text-[15px] font-medium text-ink outline-none placeholder:text-ink-soft/70";

  return (
    <form onSubmit={submit} className="max-w-4xl rounded-[28px] bg-white p-2 text-ink shadow-lift">
      <div role="tablist" className="flex gap-1 px-2 pt-1">
        {(["guided", "free"] as const).map((m) => (
          <button key={m} type="button" role="tab" aria-selected={mode === m} onClick={() => setMode(m)}
            className={clsx("relative rounded-full px-4 py-1.5 text-sm font-semibold transition", mode === m ? "text-ink" : "text-ink-soft hover:text-ink")}>
            {mode === m && <motion.span layoutId="mode-pill" className="absolute inset-0 -z-0 rounded-full bg-sand" transition={{ type: "spring", bounce: 0.25, duration: 0.5 }} />}
            <span className="relative">{m === "guided" ? "Guided" : "Describe it"}</span>
          </button>
        ))}
      </div>

      <div className="mt-1 flex flex-col gap-1 md:flex-row md:items-center">
        {mode === "guided" ? (
          <>
            <label className={field}>
              <span className={label}><MapPin className="size-3.5" />Where to</span>
              <input ref={whereRef} value={where} onChange={(e) => setWhere(e.target.value)} placeholder="Lisbon, Kyoto, anywhere warm…" className={input} />
            </label>
            <Divider />
            <label className={field}>
              <span className={label}><Calendar className="size-3.5" />When</span>
              <input value={when} onChange={(e) => setWhen(e.target.value)} placeholder="May, 5 days" className={input} />
            </label>
            <Divider />
            <div className={field}>
              <span className={label}><Users className="size-3.5" />Travelers</span>
              <div className="flex items-center gap-3">
                <Step label="Fewer travelers" onClick={() => setWho((n) => Math.max(1, n - 1))}><Minus className="size-3.5" /></Step>
                <span className="w-5 text-center text-[15px] font-semibold tabular-nums">{who}</span>
                <Step label="More travelers" onClick={() => setWho((n) => Math.min(12, n + 1))}><Plus className="size-3.5" /></Step>
              </div>
            </div>
            <Divider />
            <label className={field}>
              <span className={label}><Wallet className="size-3.5" />Budget</span>
              <select value={budget} onChange={(e) => setBudget(e.target.value)} className={clsx(input, "cursor-pointer appearance-none")}>
                <option value="">Flexible</option>
                {["$1,500", "$3,000", "$5,000", "$8,000", "$12,000"].map((b) => <option key={b} value={b}>{b}</option>)}
              </select>
            </label>
          </>
        ) : (
          <label className={clsx(field, "md:py-4")}>
            <span className={label}><Sparkles className="size-3.5" />Describe your trip</span>
            <input value={free} onChange={(e) => setFree(e.target.value)} placeholder={IDEAS[idea]} className={input} autoFocus />
          </label>
        )}
        <button type="submit" disabled={starting}
          className="group m-1 flex h-14 shrink-0 items-center justify-center gap-2 rounded-[20px] bg-coral px-7 font-semibold text-white transition hover:bg-coral-deep disabled:opacity-60 md:h-16">
          {starting ? <span className="size-5 animate-spin rounded-full border-2 border-white/40 border-t-white" /> : <>Plan it <ArrowRight className="size-5 transition-transform group-hover:translate-x-1" /></>}
        </button>
      </div>
    </form>
  );
}

const Divider = () => <span aria-hidden className="hidden h-10 w-px bg-line md:block" />;
const Step = ({ children, label, onClick }: { children: React.ReactNode; label: string; onClick: () => void }) => (
  <button type="button" aria-label={label} onClick={onClick} className="grid size-7 place-items-center rounded-full border border-line transition hover:border-ink">{children}</button>
);
