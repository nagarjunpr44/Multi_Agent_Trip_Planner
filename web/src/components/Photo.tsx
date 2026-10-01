"use client";

import { useState } from "react";
import clsx from "clsx";
import { tone } from "@/lib/images";

// A photo slot: shows `src` when it loads, otherwise a cinematic dusk landscape placeholder.
export function Photo({ src, label, className, priority, children }: {
  src?: string;
  label: string;
  className?: string;
  priority?: boolean;
  children?: React.ReactNode;
}) {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [sky, mid, ground] = tone(label);
  const showImg = src && !failed;

  return (
    <div className={clsx("relative overflow-hidden bg-night-2", className)}>
      {/* Placeholder — always underneath so the swap to a real photo is seamless */}
      <div aria-hidden className="absolute inset-0" style={{ background: `linear-gradient(170deg, ${sky} 0%, ${mid} 58%, ${ground} 100%)` }}>
        <div className="absolute left-[64%] top-[24%] aspect-square w-[12%] -translate-x-1/2 rounded-full opacity-80 blur-[1px]" style={{ background: "#ffe9c9", boxShadow: "0 0 60px 18px rgb(255 214 170 / 0.55)" }} />
        <svg viewBox="0 0 400 200" preserveAspectRatio="none" className="absolute inset-x-0 bottom-0 h-[58%] w-full">
          <path d="M0 105 L40 70 L70 92 L120 48 L165 88 L210 60 L260 96 L300 66 L345 90 L400 72 V200 H0Z" fill={ground} opacity=".5" />
          <path d="M0 140 Q80 105 170 135 T400 125 V200 H0Z" fill={ground} opacity=".85" />
        </svg>
        <div className="grain absolute inset-0" />
        <div className="absolute inset-0 shadow-[inset_0_0_80px_rgb(0_0_0/0.45)]" />
      </div>
      {showImg && (
        // eslint-disable-next-line @next/next/no-img-element -- static export: plain <img> with lazy loading
        <img
          src={src}
          alt={label}
          loading={priority ? "eager" : "lazy"}
          referrerPolicy="no-referrer"
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
          className={clsx("absolute inset-0 h-full w-full object-cover transition-opacity duration-700", loaded ? "opacity-100" : "opacity-0")}
        />
      )}
      {children}
    </div>
  );
}
