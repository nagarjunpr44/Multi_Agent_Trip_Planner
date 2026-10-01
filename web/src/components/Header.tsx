"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ChevronDown, Plus } from "lucide-react";
import clsx from "clsx";
import { listTrips } from "@/lib/api";
import type { TripSummary } from "@/lib/types";
import { dateRange } from "@/lib/format";

export function Logo({ light }: { light?: boolean }) {
  return (
    <Link href="/" className={clsx("group flex items-center gap-2.5", light ? "text-white" : "text-ink")} aria-label="Wayfarer home">
      <svg viewBox="0 0 32 32" className="size-8 transition-transform duration-500 group-hover:-rotate-12" aria-hidden>
        <rect width="32" height="32" rx="9" className={light ? "fill-white/15" : "fill-ink"} />
        <path d="M8 21c4-9 12-12 16-11" stroke="#ff5b3a" strokeWidth="2.6" fill="none" strokeLinecap="round" />
        <circle cx="8" cy="21" r="2.6" fill="#f6f2ec" />
        <circle cx="24" cy="10" r="2.6" fill="#ff5b3a" />
      </svg>
      <span className="font-display text-[26px] leading-none tracking-tight">Wayfarer</span>
    </Link>
  );
}

// overlay: transparent over the hero until scrolled. solid: app chrome.
export function Header({ variant = "solid", onNewTrip }: { variant?: "overlay" | "solid"; onNewTrip: () => void }) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    if (variant !== "overlay") return;
    const onScroll = () => setScrolled(window.scrollY > 40);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [variant]);
  const light = variant === "overlay" && !scrolled;

  return (
    <header
      className={clsx(
        "z-40 transition-[background,box-shadow,color] duration-500",
        variant === "overlay" ? "fixed inset-x-0 top-0" : "relative border-b border-line bg-white",
        variant === "overlay" && scrolled && "bg-white/85 shadow-card backdrop-blur-xl",
      )}
    >
      <div className={clsx("mx-auto flex items-center gap-6 px-4 sm:px-6", variant === "overlay" ? "h-20 max-w-7xl" : "h-16")}>
        <Logo light={light} />
        {variant === "overlay" && (
          <nav className={clsx("ml-6 hidden gap-7 text-[15px] font-medium md:flex", light ? "text-white/85" : "text-ink-soft")}>
            <a href="#destinations" className="hover:text-coral">Destinations</a>
            <a href="#how" className="hover:text-coral">How it works</a>
          </nav>
        )}
        <div className="ml-auto flex items-center gap-2">
          <MyTrips light={light} />
          <button
            onClick={onNewTrip}
            className={clsx(
              "flex items-center gap-1.5 rounded-full px-4 py-2.5 text-sm font-semibold transition hover:-translate-y-px active:translate-y-0",
              light ? "bg-white text-ink hover:bg-coral hover:text-white" : "bg-ink text-white hover:bg-coral",
            )}
          >
            <Plus className="size-4" /> <span className="hidden sm:inline">Plan a trip</span><span className="sm:hidden">New</span>
          </button>
        </div>
      </div>
    </header>
  );
}

function MyTrips({ light }: { light: boolean }) {
  const [open, setOpen] = useState(false);
  const [trips, setTrips] = useState<TripSummary[] | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    listTrips().then(setTrips).catch(() => setTrips([]));
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className={clsx("flex items-center gap-1 rounded-full px-4 py-2.5 text-sm font-semibold transition", light ? "text-white hover:bg-white/15" : "hover:bg-sand")}
      >
        My trips <ChevronDown className={clsx("size-4 transition-transform", open && "rotate-180")} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.98 }}
            transition={{ duration: 0.18 }}
            className="absolute right-0 top-full z-50 mt-2 w-80 origin-top-right overflow-hidden rounded-2xl border border-line bg-white p-2 text-ink shadow-lift"
          >
            {trips === null && <div className="h-24 animate-shimmer rounded-xl bg-[linear-gradient(90deg,#f6f2ec,#fff,#f6f2ec)] bg-[length:200%_100%]" />}
            {trips?.length === 0 && <p className="p-4 text-sm text-ink-soft">No trips yet. Plan your first one.</p>}
            <ul className="max-h-96 overflow-y-auto">
              {trips?.map((t) => (
                <li key={t.id}>
                  <Link href={`/plan?id=${t.id}`} onClick={() => setOpen(false)} className="block rounded-xl px-3 py-2.5 hover:bg-sand">
                    <div className="truncate font-semibold">{t.title || "Untitled trip"}</div>
                    <div className="text-xs text-ink-soft">{dateRange(t.start_date, t.end_date)} · {t.status.replace("_", " ")}</div>
                  </Link>
                </li>
              ))}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
