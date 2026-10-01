"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, Marker, Polyline, Popup, TileLayer, useMap, useMapEvent } from "react-leaflet";
import L from "leaflet";
import clsx from "clsx";
import { hhmm } from "@/lib/format";
import type { Trip } from "@/lib/types";
import { DAY_COLORS } from "./Itinerary";

// OpenStreetMap's tiles are fine for development and light use; for production traffic set
// NEXT_PUBLIC_MAP_TILES (+ NEXT_PUBLIC_MAP_ATTRIBUTION) to a provider such as MapTiler or Stadia.
const TILES = process.env.NEXT_PUBLIC_MAP_TILES ?? "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTRIBUTION = process.env.NEXT_PUBLIC_MAP_ATTRIBUTION ?? '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

type Pt = { id: string; lat: number; lng: number; n: number; day: number; name: string; time: string };

// Numbers and colors only — never trip text — go into the marker HTML.
const pinIcon = (n: number | string, color: string, cls = "") =>
  L.divIcon({ className: "", html: `<div class="pin ${cls}" style="background:${color}">${n}</div>`, iconSize: [30, 30], iconAnchor: [15, 15] });

function Fit({ points, selected }: { points: Pt[]; selected: number | null }) {
  const map = useMap();
  const key = `${selected}:${points.length}`;
  const prev = useRef("");
  const first = useRef(true);
  const [resized, setResized] = useState(0);
  useMapEvent("resize", () => setResized((n) => n + 1));
  useEffect(() => {
    // A hidden pane (mobile tabs) has zero size; fitting then yields NaN. Fit once it's shown.
    map.invalidateSize();
    if (!map.getSize().x || prev.current === key) return;
    prev.current = key;
    const pts = selected == null ? points : points.filter((p) => p.day === selected);
    if (!pts.length) return;
    const bounds = L.latLngBounds(pts.map((p) => [p.lat, p.lng]));
    const opts = { padding: [60, 60] as [number, number], maxZoom: 15 };
    // First framing is instant; later day switches fly.
    if (first.current) { first.current = false; map.fitBounds(bounds, { ...opts, animate: false }); }
    else map.flyToBounds(bounds, { ...opts, duration: 0.9 });
  }, [key, map, points, selected, resized]);
  return null;
}

// Leaflet caches its size; panes toggle on small screens, so re-measure on resize.
function AutoSize() {
  const map = useMap();
  useEffect(() => {
    // No animated pan: it would interrupt an in-flight flyToBounds.
    const ro = new ResizeObserver(() => map.invalidateSize({ animate: false }));
    ro.observe(map.getContainer());
    return () => ro.disconnect();
  }, [map]);
  return null;
}

export default function TripMap({ trip, activeDay, onActiveDay, hoverStop, className }: {
  trip?: Trip;
  activeDay: number;
  onActiveDay: (i: number) => void;
  hoverStop: string | null;
  className?: string;
}) {
  const points = useMemo<Pt[]>(() =>
    (trip?.days ?? []).flatMap((d, day) =>
      d.stops.filter((s) => s.place.lat != null && s.place.lng != null)
        .map((s, i) => ({ id: s.id, lat: s.place.lat!, lng: s.place.lng!, n: i + 1, day, name: s.place.name, time: hhmm(s.start) }))),
  [trip]);
  const hotel = trip?.hotel?.lat != null && trip.hotel.lng != null ? trip.hotel : null;
  const hasDays = (trip?.days.length ?? 0) > 0;
  const selected = hasDays ? activeDay : null;
  const center: [number, number] = points[0] ? [points[0].lat, points[0].lng] : hotel ? [hotel.lat!, hotel.lng!] : [30, 0];

  return (
    <section aria-label="Map" className={clsx("relative min-h-0", className)}>
      <MapContainer center={center} zoom={points.length || hotel ? 13 : 2} zoomControl={false} scrollWheelZoom className="h-full w-full">
        <TileLayer url={TILES} attribution={ATTRIBUTION} />
        <AutoSize />
        <Fit points={points} selected={selected} />
        {(trip?.days ?? []).map((d, day) => {
          const line = points.filter((p) => p.day === day).map((p) => [p.lat, p.lng] as [number, number]);
          const on = selected == null || selected === day;
          return line.length > 1 ? (
            <Polyline key={d.date} positions={line} pathOptions={{ color: DAY_COLORS[day % DAY_COLORS.length], weight: on ? 4 : 2, opacity: on ? 0.9 : 0.25, dashArray: on ? undefined : "4 8" }} />
          ) : null;
        })}
        {points.map((p) => {
          const on = selected == null || selected === p.day;
          return (
            <Marker key={p.id} position={[p.lat, p.lng]} opacity={on ? 1 : 0.35} zIndexOffset={hoverStop === p.id ? 1000 : on ? 100 : 0}
              icon={pinIcon(p.n, DAY_COLORS[p.day % DAY_COLORS.length], hoverStop === p.id ? "active" : "")}
              eventHandlers={{ click: () => onActiveDay(p.day) }}>
              <Popup><strong>{p.name}</strong><br />Day {p.day + 1} · {p.time}</Popup>
            </Marker>
          );
        })}
        {hotel && (
          <Marker position={[hotel.lat!, hotel.lng!]} icon={pinIcon("⌂", "#1f8f80", "hotel")}>
            <Popup><strong>{hotel.name}</strong><br />Your stay</Popup>
          </Marker>
        )}
      </MapContainer>

      {hasDays && (
        <div className="pointer-events-none absolute inset-x-0 top-0 z-[500] flex gap-2 overflow-x-auto p-3 [scrollbar-width:none]">
          {trip!.days.map((d, i) => (
            <button key={d.date} onClick={() => onActiveDay(i)}
              className={clsx("pointer-events-auto flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold shadow-card backdrop-blur-xl transition", i === activeDay ? "bg-white text-ink" : "bg-night/70 text-white ring-1 ring-rim hover:bg-night/90")}>
              <span className="size-2 rounded-full" style={{ background: DAY_COLORS[i % DAY_COLORS.length] }} />Day {i + 1}
            </button>
          ))}
        </div>
      )}
      {!points.length && (
        <div className="pointer-events-none absolute inset-0 z-[500] grid place-items-center">
          <p className="glass-panel rounded-full px-4 py-2 text-sm font-medium text-mist">Places will pin themselves here</p>
        </div>
      )}
    </section>
  );
}
