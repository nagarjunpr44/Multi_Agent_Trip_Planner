"use client";

import Link from "next/link";
import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { CalendarRange, MessageCircle } from "lucide-react";
import clsx from "clsx";
import { Header } from "@/components/Header";
import { Ambient, scenePoster } from "@/components/Ambient";
import { tripCover } from "@/lib/images";
import { useStartTrip } from "@/lib/useStartTrip";
import { ChatPanel } from "./ChatPanel";
import { Itinerary } from "./Itinerary";
import { useTrip } from "./useTrip";

type Pane = "chat" | "plan";

/*
  Layout:
    ≥1024px  chat | itinerary, side by side
    <1024px  one pane at a time, bottom tab bar
*/
export function Workspace() {
  const id = useSearchParams().get("id");
  const { state, msgs, busy, loadError, send, answer } = useTrip(id);
  const { start } = useStartTrip();
  const [pane, setPane] = useState<Pane>("chat");

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

  const tabs: { key: Pane; label: string; icon: typeof MessageCircle }[] = [
    { key: "chat", label: "Chat", icon: MessageCircle },
    { key: "plan", label: "Itinerary", icon: CalendarRange },
  ];

  return (
    <div className="relative isolate flex h-dvh flex-col overflow-hidden">
      {/* The trip's own photo (or a hero scene) as blurred mood light behind the glass panels */}
      <Ambient src={tripCover(state?.trip) ?? scenePoster(id)} />
      <Header onNewTrip={() => start()} />
      <div className="relative grid min-h-0 flex-1 grid-cols-1 gap-3 p-2 sm:p-3 lg:grid-cols-[400px_minmax(0,1fr)] xl:grid-cols-[440px_minmax(0,1fr)]">
        <ChatPanel msgs={msgs} busy={busy} trip={state?.trip} onSend={send} onAnswer={answer}
          className={clsx("glass-panel overflow-hidden rounded-3xl", pane === "chat" ? "flex" : "hidden", "lg:flex")} />

        <div className={clsx("glass-panel relative min-h-0 flex-col overflow-hidden rounded-3xl", pane === "plan" ? "flex" : "hidden", "lg:flex")}>
          <Itinerary state={state} busy={busy} onReview={() => setPane("chat")} className="flex flex-1" />
        </div>
      </div>

      {/* <1024: bottom tab bar */}
      <nav aria-label="Views" className="grid grid-cols-2 border-t border-rim bg-night/70 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl lg:hidden">
        {tabs.map((t) => (
          <button key={t.key} onClick={() => setPane(t.key)} aria-current={pane === t.key}
            className={clsx("relative flex flex-col items-center gap-0.5 py-2.5 text-xs font-semibold transition", pane === t.key ? "text-coral" : "text-haze")}>
            <t.icon className="size-5" />{t.label}
            {t.key === "plan" && state?.trip.status === "awaiting_approval" && <span className="absolute right-[35%] top-2 size-2 rounded-full bg-coral" />}
          </button>
        ))}
      </nav>
    </div>
  );
}
