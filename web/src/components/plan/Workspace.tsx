"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CalendarRange, Map as MapIcon, MessageCircle } from "lucide-react";
import clsx from "clsx";
import { Header } from "@/components/Header";
import { Ambient, scenePoster } from "@/components/Ambient";
import { tripCover } from "@/lib/images";
import { useStartTrip } from "@/lib/useStartTrip";
import { ChatPanel } from "./ChatPanel";
import { Itinerary } from "./Itinerary";
import { useTrip } from "./useTrip";

// Leaflet touches `window`, so the map only loads in the browser.
const TripMap = dynamic(() => import("./TripMap"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse rounded-3xl bg-white/5" />,
});

type Pane = "chat" | "plan" | "map";

/*
  Layout (Mindtrip / Wanderlog pattern):
    ≥1280px  chat | itinerary | map, all visible
    ≥1024px  chat | itinerary-or-map (toggle)
    <1024px  one pane at a time, bottom tab bar
*/
export function Workspace() {
  const id = useSearchParams().get("id");
  const { state, msgs, busy, loadError, send, answer } = useTrip(id);
  const { start } = useStartTrip();
  const [pane, setPane] = useState<Pane>("chat");
  const [activeDay, setActiveDay] = useState(0);
  const [hoverStop, setHoverStop] = useState<string | null>(null);
  const onActiveDay = useCallback((i: number) => setActiveDay(i), []);

  if (!id || loadError) {
    return (
      <div className="relative isolate flex min-h-dvh flex-col">
        <Ambient src={scenePoster(id ?? "")} />
        <Header onNewTrip={() => start()} />
        <div className="glass-panel m-auto max-w-sm rounded-3xl p-8 text-center">
          <p className="font-display text-4xl">{id ? "Trip not found" : "No trip selected"}</p>
          <p className="mt-2 text-mist">{loadError ?? "Start a new trip or pick one from My trips."}</p>
          <Link href="/" className="mt-6 inline-block rounded-full bg-coral px-6 py-3 font-semibold text-white hover:bg-coral-deep">Back home</Link>
        </div>
      </div>
    );
  }

  const tabs: { key: Pane; label: string; icon: typeof MapIcon }[] = [
    { key: "chat", label: "Chat", icon: MessageCircle },
    { key: "plan", label: "Itinerary", icon: CalendarRange },
    { key: "map", label: "Map", icon: MapIcon },
  ];

  return (
    <div className="relative isolate flex h-dvh flex-col overflow-hidden">
      {/* The trip's own photo (or a hero scene) as blurred mood light behind the glass panels */}
      <Ambient src={tripCover(state?.trip) ?? scenePoster(id)} />
      <Header onNewTrip={() => start()} />
      <div className="relative grid min-h-0 flex-1 grid-cols-1 gap-3 p-2 sm:p-3 lg:grid-cols-[400px_minmax(0,1fr)] xl:grid-cols-[400px_minmax(520px,1.1fr)_minmax(0,1fr)]">
        <ChatPanel msgs={msgs} busy={busy} trip={state?.trip} onSend={send} onAnswer={answer}
          className={clsx("glass-panel overflow-hidden rounded-3xl", pane === "chat" ? "flex" : "hidden", "lg:flex")} />

        <div className={clsx("glass-panel relative min-h-0 flex-col overflow-hidden rounded-3xl", pane === "plan" ? "flex" : "hidden", pane === "map" ? "xl:flex" : "lg:flex")}>
          <Itinerary state={state} busy={busy} activeDay={activeDay} onActiveDay={onActiveDay} hoverStop={hoverStop} onHoverStop={setHoverStop}
            onReview={() => setPane("chat")} className="flex flex-1" />
        </div>

        <TripMap trip={state?.trip} activeDay={activeDay} onActiveDay={onActiveDay} hoverStop={hoverStop}
          className={clsx("overflow-hidden rounded-3xl shadow-lift ring-1 ring-rim", pane === "map" ? "block" : "hidden", "xl:block")} />

        {/* ≥1024 & <1280: itinerary/map toggle floats over the second column */}
        <div className="glass-panel absolute right-6 top-6 z-[600] hidden rounded-full p-1 lg:flex xl:hidden">
          {tabs.slice(1).map((t) => (
            <button key={t.key} onClick={() => setPane(t.key)} aria-pressed={(pane === "map") === (t.key === "map")}
              className={clsx("relative flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-semibold transition", (pane === "map") === (t.key === "map") ? "bg-white text-ink" : "text-mist hover:text-white")}>
              <t.icon className="size-4" />{t.label}
            </button>
          ))}
        </div>
      </div>

      {/* <1024: bottom tab bar */}
      <nav aria-label="Views" className="grid grid-cols-3 border-t border-rim bg-night/70 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl lg:hidden">
        {tabs.map((t) => (
          <button key={t.key} onClick={() => setPane(t.key)} aria-current={pane === t.key}
            className={clsx("relative flex flex-col items-center gap-0.5 py-2.5 text-xs font-semibold transition", pane === t.key ? "text-coral" : "text-haze")}>
            <t.icon className="size-5" />{t.label}
            {t.key === "plan" && state?.trip.status === "awaiting_approval" && <span className="absolute right-[30%] top-2 size-2 rounded-full bg-coral" />}
          </button>
        ))}
      </nav>
    </div>
  );
}
