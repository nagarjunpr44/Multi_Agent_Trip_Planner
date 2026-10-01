"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useState } from "react";
import { useSearchParams } from "next/navigation";
import { CalendarRange, Map as MapIcon, MessageCircle } from "lucide-react";
import clsx from "clsx";
import { Header } from "@/components/Header";
import { useStartTrip } from "@/lib/useStartTrip";
import { ChatPanel } from "./ChatPanel";
import { Itinerary } from "./Itinerary";
import { useTrip } from "./useTrip";

// Leaflet touches `window`, so the map only loads in the browser.
const TripMap = dynamic(() => import("./TripMap"), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse bg-sand-2" />,
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
      <div className="flex min-h-dvh flex-col">
        <Header onNewTrip={() => start()} />
        <div className="m-auto max-w-sm p-6 text-center">
          <p className="font-display text-4xl">{id ? "Trip not found" : "No trip selected"}</p>
          <p className="mt-2 text-ink-soft">{loadError ?? "Start a new trip or pick one from My trips."}</p>
          <Link href="/" className="mt-6 inline-block rounded-full bg-ink px-6 py-3 font-semibold text-white hover:bg-coral">Back home</Link>
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
    <div className="flex h-dvh flex-col overflow-hidden">
      <Header onNewTrip={() => start()} />
      <div className="relative grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[400px_minmax(0,1fr)] xl:grid-cols-[400px_minmax(520px,1.1fr)_minmax(0,1fr)]">
        <ChatPanel msgs={msgs} busy={busy} trip={state?.trip} onSend={send} onAnswer={answer}
          className={clsx(pane === "chat" ? "flex" : "hidden", "lg:flex")} />

        <div className={clsx("relative min-h-0 flex-col", pane === "plan" ? "flex" : "hidden", pane === "map" ? "xl:flex" : "lg:flex")}>
          <Itinerary state={state} busy={busy} activeDay={activeDay} onActiveDay={onActiveDay} hoverStop={hoverStop} onHoverStop={setHoverStop}
            onReview={() => setPane("chat")} className="flex flex-1" />
        </div>

        <TripMap trip={state?.trip} activeDay={activeDay} onActiveDay={onActiveDay} hoverStop={hoverStop}
          className={clsx(pane === "map" ? "block" : "hidden", "border-l border-line xl:block")} />

        {/* ≥1024 & <1280: itinerary/map toggle floats over the second column */}
        <div className="absolute right-4 top-4 z-[600] hidden rounded-full bg-white p-1 shadow-card lg:flex xl:hidden">
          {tabs.slice(1).map((t) => (
            <button key={t.key} onClick={() => setPane(t.key)} aria-pressed={(pane === "map") === (t.key === "map")}
              className={clsx("flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-semibold transition", (pane === "map") === (t.key === "map") ? "bg-ink text-white" : "text-ink-soft")}>
              <t.icon className="size-4" />{t.label}
            </button>
          ))}
        </div>
      </div>

      {/* <1024: bottom tab bar */}
      <nav aria-label="Views" className="grid grid-cols-3 border-t border-line bg-white pb-[env(safe-area-inset-bottom)] lg:hidden">
        {tabs.map((t) => (
          <button key={t.key} onClick={() => setPane(t.key)} aria-current={pane === t.key}
            className={clsx("relative flex flex-col items-center gap-0.5 py-2.5 text-xs font-semibold transition", pane === t.key ? "text-coral" : "text-ink-soft")}>
            <t.icon className="size-5" />{t.label}
            {t.key === "plan" && state?.trip.status === "awaiting_approval" && <span className="absolute right-[30%] top-2 size-2 rounded-full bg-coral" />}
          </button>
        ))}
      </nav>
    </div>
  );
}
