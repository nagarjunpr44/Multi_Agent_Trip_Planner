"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ChevronDown, Menu, Plus, X } from "lucide-react";
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
      <span className="font-display text-xl italic leading-none tracking-tight sm:text-2xl">Wayfarer</span>
    </Link>
  );
}

const LINKS = [
  { href: "#destinations", label: "Destinations" },
  { href: "#trips", label: "Your trips" },
  { href: "#how", label: "How it works" },
];

// overlay: liquid glass over the hero, solid once scrolled past it. solid: app chrome.
export function Header({ variant = "solid", onNewTrip }: { variant?: "overlay" | "solid"; onNewTrip: () => void }) {
  const [scrolled, setScrolled] = useState(false);
  const [menu, setMenu] = useState(false);

  useEffect(() => {
    if (variant !== "overlay") return;
    const onScroll = () => setScrolled(window.scrollY > window.innerHeight * 0.85);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [variant]);

  // Mobile menu: lock page scroll, close on Escape.
  useEffect(() => {
    if (!menu) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenu(false);
    document.addEventListener("keydown", onKey);
    return () => { document.body.style.overflow = prev; document.removeEventListener("keydown", onKey); };
  }, [menu]);

  if (variant === "solid") {
    return (
      <header className="relative z-40 border-b border-line bg-white">
        <div className="flex h-16 items-center gap-6 px-4 sm:px-6">
          <Logo />
          <div className="ml-auto flex items-center gap-2">
            <MyTrips light={false} />
            <button onClick={onNewTrip} className="flex items-center gap-1.5 rounded-full bg-ink px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-coral">
              <Plus className="size-4" /> <span className="hidden sm:inline">Plan a trip</span><span className="sm:hidden">New</span>
            </button>
          </div>
        </div>
      </header>
    );
  }

  const light = !scrolled;
  return (
    <>
      {/* Above the mobile menu overlay while it's open, so the X stays tappable */}
      <header className={clsx("fixed inset-x-0 top-0 transition-[background,box-shadow] duration-500", menu ? "z-[60]" : "z-40", scrolled && !menu && "bg-white/85 shadow-card backdrop-blur-xl")}>
        <div className={clsx("mx-auto flex max-w-7xl items-center justify-between px-5 transition-[height] duration-500 sm:px-8", scrolled ? "h-16" : "h-20 sm:h-24")}>
          <Logo light={light} />

          {/* Desktop: glass pill */}
          <nav className={clsx("hidden items-center gap-1 rounded-full p-1.5 pl-5 text-sm md:flex", light ? "liquid-glass overflow-visible bg-black/15 text-white/90" : "border border-line bg-white text-ink-soft")}>
            {/* bg-black/15: keeps white links legible over bright scenes (e.g. Winter Light) */}
            {LINKS.filter((l) => l.href !== "#trips").map((l) => (
              <a key={l.href} href={l.href} className={clsx("rounded-full px-3 py-2 transition-colors", light ? "hover:text-white" : "hover:text-ink")}>{l.label}</a>
            ))}
            <MyTrips light={light} />
            <button onClick={onNewTrip} className={clsx("ml-1 rounded-full px-5 py-2.5 font-semibold transition-colors", light ? "bg-white text-ink hover:bg-white/90" : "bg-ink text-white hover:bg-coral")}>
              Plan a trip
            </button>
          </nav>

          {/* Mobile: glass hamburger with Menu ⇄ X crossfade */}
          <button
            onClick={() => setMenu((m) => !m)}
            aria-label={menu ? "Close menu" : "Open menu"}
            aria-expanded={menu}
            className={clsx("relative z-[60] grid size-11 place-items-center rounded-full md:hidden", light || menu ? "liquid-glass text-white" : "border border-line bg-white text-ink")}
          >
            <Menu className={clsx("absolute size-5 transition-all duration-300", menu ? "rotate-90 scale-75 opacity-0" : "rotate-0 scale-100 opacity-100")} />
            <X className={clsx("absolute size-5 transition-all duration-300", menu ? "rotate-0 scale-100 opacity-100" : "-rotate-90 scale-75 opacity-0")} />
          </button>
        </div>
      </header>

      <MobileMenu open={menu} onClose={() => setMenu(false)} onNewTrip={() => { setMenu(false); onNewTrip(); }} />
    </>
  );
}

function MobileMenu({ open, onClose, onNewTrip }: { open: boolean; onClose: () => void; onNewTrip: () => void }) {
  const ease = "ease-[cubic-bezier(0.4,0,0.2,1)] duration-500";
  return (
    <div
      className={clsx("fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/60 backdrop-blur-sm transition-opacity md:hidden", ease, open ? "opacity-100" : "pointer-events-none opacity-0")}
      onClick={onClose}
      aria-hidden={!open}
    >
      <nav className="flex flex-col items-center gap-7" onClick={(e) => e.stopPropagation()}>
        {LINKS.map((l, i) => (
          <a
            key={l.href}
            href={l.href}
            onClick={onClose}
            tabIndex={open ? 0 : -1}
            style={{ transitionDelay: open ? `${100 + i * 50}ms` : "0ms" }}
            className={clsx("font-display text-3xl text-white transition-all", ease, open ? "translate-y-0 opacity-100" : "translate-y-4 opacity-0")}
          >
            {l.label}
          </a>
        ))}
        <button
          onClick={onNewTrip}
          tabIndex={open ? 0 : -1}
          style={{ transitionDelay: open ? `${100 + LINKS.length * 50}ms` : "0ms" }}
          className={clsx("mt-4 rounded-full bg-white px-8 py-3.5 font-semibold text-ink transition-all", ease, open ? "scale-100 opacity-100" : "scale-90 opacity-0")}
        >
          Plan a trip
        </button>
      </nav>
    </div>
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
        className={clsx("flex items-center gap-1 rounded-full px-3 py-2 text-sm transition-colors", light ? "hover:text-white" : "font-semibold hover:bg-sand hover:text-ink")}
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
            className="absolute right-0 top-full z-50 mt-3 w-80 origin-top-right overflow-hidden rounded-2xl border border-line bg-white p-2 text-left text-ink shadow-lift"
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
