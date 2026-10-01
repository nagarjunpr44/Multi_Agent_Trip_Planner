"use client";

import { useState } from "react";
import clsx from "clsx";

// The hero's scenes, reused as mood lighting on every other page.
export const SCENE_POSTERS = [1, 2, 3, 4].map((n) => `/images/hero/scene-${n}.webp`);

export function scenePoster(seed = "") {
  let h = 0;
  for (const c of seed) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return SCENE_POSTERS[h % SCENE_POSTERS.length];
}

// Fixed, heavily blurred backdrop: reads as colored light, not as a picture (so a generic scene
// behind a specific trip never pretends to be that destination).
export function Ambient({ src, className }: { src: string; className?: string }) {
  const [loaded, setLoaded] = useState<string | null>(null);
  return (
    <div aria-hidden className={clsx("pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-night", className)}>
      {/* eslint-disable-next-line @next/next/no-img-element -- static export, decorative */}
      <img
        key={src}
        src={src}
        alt=""
        onLoad={() => setLoaded(src)}
        className={clsx("absolute inset-0 h-full w-full animate-drift object-cover blur-[70px] brightness-[0.55] saturate-[1.4] transition-opacity duration-1000", loaded === src ? "opacity-100" : "opacity-0")}
      />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,transparent_0%,rgb(9_16_23/0.55)_70%)]" />
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-night/30 to-night/80" />
      <div className="grain absolute inset-0" />
    </div>
  );
}
