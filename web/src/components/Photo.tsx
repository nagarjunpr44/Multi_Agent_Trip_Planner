"use client";

import { useState } from "react";
import clsx from "clsx";
import { tone } from "@/lib/images";

// A photo slot: shows `src` when it loads, otherwise an illustrated gradient landscape.
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
    <div className={clsx("relative overflow-hidden bg-sand-2", className)}>
      {/* Placeholder landscape — always rendered underneath so the swap is seamless */}
      <div aria-hidden className="absolute inset-0" style={{ background: `linear-gradient(170deg, ${sky} 0%, ${mid} 62%, ${ground} 100%)` }}>
        <div className="absolute left-[62%] top-[26%] aspect-square w-[13%] -translate-x-1/2 rounded-full opacity-70" style={{ background: sky, boxShadow: `0 0 80px 20px ${sky}` }} />
        <svg viewBox="0 0 400 200" preserveAspectRatio="none" className="absolute inset-x-0 bottom-0 h-[55%] w-full">
          <path d="M0 110 Q60 60 120 95 T240 80 T400 95 V200 H0Z" fill={ground} opacity=".45" />
          <path d="M0 150 Q80 110 170 140 T400 130 V200 H0Z" fill={ground} opacity=".8" />
        </svg>
      </div>
      {showImg && (
        // eslint-disable-next-line @next/next/no-img-element -- static export: plain <img> with lazy loading
        <img
          src={src}
          alt={label}
          loading={priority ? "eager" : "lazy"}
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
          className={clsx("absolute inset-0 h-full w-full object-cover transition-opacity duration-700", loaded ? "opacity-100" : "opacity-0")}
        />
      )}
      {children}
    </div>
  );
}
