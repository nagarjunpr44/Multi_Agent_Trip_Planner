"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { ArrowRight, Pause, Play } from "lucide-react";
import clsx from "clsx";

// Window-seat hero: landscapes roll past a train window (overlay), one scene at a time.
// Videos stream from a CDN (~15-25 MB each), so only the visible one loads; the rest load
// when picked. Posters (public/images/hero/scene-N.webp) are the videos' first frames, so the
// still-to-motion swap is seamless. For production, self-host the MP4s and update `src`.
const CDN = "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P";
const SCENES = [
  { label: "Lavender Dusk", src: `${CDN}/hf_20260702_081127_0992a171-d3c6-4978-8213-0ec5df8b6d63.mp4`, dark: false },
  { label: "Still Water", src: `${CDN}/hf_20260702_092026_dd05b805-ea0f-40b2-8c52-332b88502592.mp4`, dark: false },
  { label: "Winter Light", src: `${CDN}/hf_20260702_081042_df7202bf-bd80-4b2b-bbc6-1f09ba2870e9.mp4`, dark: true }, // bright scene → dark text
  { label: "Golden Hour", src: `${CDN}/hf_20260702_080959_4cac5234-3573-464e-a5b7-76b94b8a7d61.mp4`, dark: false },
].map((s, i) => ({ ...s, poster: `/images/hero/scene-${i + 1}.webp` }));

const FADE_MS = 1000; // matches the CSS crossfade; clicks during it are ignored

const IDEAS = [
  "5 days in Lisbon in May, 2 people, ~$3000",
  "A slow week in Kyoto in cherry blossom season",
  "Long weekend in Mexico City for tacos and museums",
  "Family trip to Barcelona in July, beaches + Gaudí",
];

// Capabilities, not vanity metrics: every line here is something the planner actually does.
const STATS = ["Live flight & hotel prices", "Opening hours checked", "Walking times between stops", "Day-by-day itineraries"];

const sans = "font-sans";

// Reduced motion or data saver → start on still posters (the visitor can still press play).
// The server snapshot assumes "still" so prerendered HTML never autoplays.
const MOTION_QUERY = "(prefers-reduced-motion: reduce)";
function prefersStill() {
  const saveData = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData;
  return matchMedia(MOTION_QUERY).matches || Boolean(saveData);
}
function subscribeMotion(onChange: () => void) {
  const mq = matchMedia(MOTION_QUERY);
  mq.addEventListener("change", onChange);
  return () => mq.removeEventListener("change", onChange);
}

export function Hero({ onStart, starting, error }: { onStart: (prompt: string) => void; starting: boolean; error: string | null }) {
  const [active, setActive] = useState(0);
  const [transitioning, setTransitioning] = useState(false);
  const [choice, setChoice] = useState<boolean | null>(null); // the visitor's play/pause, once they press it
  const still = useSyncExternalStore(subscribeMotion, prefersStill, () => true);
  const playing = choice ?? !still;
  const videos = useRef<(HTMLVideoElement | null)[]>([]);
  const cooldown = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => { if (cooldown.current) clearTimeout(cooldown.current); }, []);

  // Play only the active scene; pause the rest once they've faded out.
  useEffect(() => {
    const timers: ReturnType<typeof setTimeout>[] = [];
    videos.current.forEach((v, i) => {
      if (!v) return;
      if (i === active && playing) {
        v.preload = "auto";
        v.play().catch(() => {}); // autoplay can be refused; the poster stays visible
      } else if (i !== active) {
        timers.push(setTimeout(() => v.pause(), FADE_MS));
      } else {
        v.pause();
      }
    });
    return () => timers.forEach(clearTimeout); // a quick switch back must not pause the new active scene
  }, [active, playing]);

  const pick = useCallback((i: number) => {
    if (i === active || transitioning) return;
    setActive(i);
    setTransitioning(true);
    cooldown.current = setTimeout(() => setTransitioning(false), FADE_MS);
  }, [active, transitioning]);

  const dark = SCENES[active].dark;

  return (
    <section className="relative h-[100svh] min-h-[620px] w-full overflow-hidden bg-black" aria-label="Plan a trip">
      {/* Background scenes */}
      {SCENES.map((s, i) => (
        <video
          key={s.src}
          ref={(el) => { videos.current[i] = el; }}
          src={s.src}
          poster={s.poster}
          muted
          loop
          playsInline
          preload={i === 0 ? "auto" : "none"}
          aria-hidden
          className={clsx("absolute inset-0 h-full w-full object-cover transition-opacity duration-1000 ease-in-out", i === active ? "opacity-100" : "opacity-0")}
        />
      ))}

      {/* Train window frame */}
      {/* eslint-disable-next-line @next/next/no-img-element -- static export, decorative overlay */}
      <img src="/images/hero/window.webp" alt="" aria-hidden className="train-bob pointer-events-none absolute inset-0 z-[1] h-full w-full object-cover" />

      {/* Soft scrim behind the copy: dark for white text, light for the bright scene's dark text */}
      <div aria-hidden className={clsx("pointer-events-none absolute inset-0 z-[1] transition-opacity duration-700 bg-[radial-gradient(ellipse_55%_45%_at_50%_42%,rgb(0_0_0/0.35),transparent)]", dark ? "opacity-0" : "opacity-100")} />
      <div aria-hidden className={clsx("pointer-events-none absolute inset-0 z-[1] transition-opacity duration-700 bg-[radial-gradient(ellipse_55%_45%_at_50%_42%,rgb(255_255_255/0.45),transparent)]", dark ? "opacity-100" : "opacity-0")} />

      {/* Content */}
      <div className="relative z-[2] flex h-full flex-col items-center px-5 pb-6 pt-28 text-center sm:px-8 sm:pb-8 sm:pt-32">
        <div className={clsx("flex w-full flex-col items-center transition-colors duration-700", dark ? "text-[#182C41]" : "text-white [text-shadow:0_2px_24px_rgb(0_0_0/0.25)]")}>
          <p className={clsx(sans, "liquid-glass rounded-full px-4 py-1.5 text-xs sm:text-sm")}>
            Real prices · real opening hours · real walking times
          </p>

          <h1 className="mt-6 max-w-4xl font-display text-4xl leading-[1.1] tracking-[-0.01em] sm:text-5xl md:text-7xl lg:text-[5.5rem]">
            Plan less, <em>wander</em>
            <br />
            further than ever
          </h1>

          <p className={clsx(sans, "mt-5 max-w-xl text-[15px] leading-relaxed opacity-90 sm:text-base")}>
            Tell Wayfarer where you&apos;re dreaming of. It searches real flights, hotels and places, then builds a day-by-day plan you can actually follow.
          </p>

          <PromptPill starting={starting} onStart={onStart} />
          {error && <p role="alert" className={clsx(sans, "mt-3 text-sm font-medium")}>Couldn&apos;t start a trip: {error}</p>}

          <div className={clsx(sans, "mt-8 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-xs sm:text-sm")} role="group" aria-label="Scenery">
            {SCENES.map((s, i) => (
              <button
                key={s.label}
                onClick={() => pick(i)}
                aria-pressed={i === active}
                className={clsx(
                  "border-b pb-1 transition-[opacity,border-color] duration-300",
                  i === active ? "border-current opacity-100" : "border-transparent opacity-50 hover:opacity-80",
                )}
              >
                {s.label}
              </button>
            ))}
            <button
              onClick={() => setChoice(!playing)}
              aria-label={playing ? "Pause background video" : "Play background video"}
              className="grid size-7 place-items-center rounded-full opacity-60 transition hover:opacity-100"
            >
              {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
            </button>
          </div>
        </div>

        <div className="flex-1" />

        {/* Stats: always white, they sit on the window frame */}
        <ul className={clsx(sans, "flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-xs text-white/70 sm:text-sm")}>
          {STATS.map((s, i) => (
            <li key={s} className="flex items-center gap-4">
              {i > 0 && <span aria-hidden className="hidden sm:inline">|</span>}
              {s}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function PromptPill({ starting, onStart }: { starting: boolean; onStart: (prompt: string) => void }) {
  const [text, setText] = useState("");
  const [idea, setIdea] = useState(0);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const t = setInterval(() => setIdea((i) => (i + 1) % IDEAS.length), 3500);
    return () => clearInterval(t);
  }, []);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (starting) return;
        if (text.trim()) onStart(text.trim());
        else input.current?.focus();
      }}
      // Dark frosted pill: same look on every scene, so the text never fights the video.
      className={clsx(sans, "glass-input mt-8 flex w-full max-w-[360px] items-center gap-1 rounded-full p-1.5 pl-5 text-white [text-shadow:none] sm:max-w-xl")}
    >
      <label htmlFor="hero-prompt" className="sr-only">Describe your trip</label>
      <input
        id="hero-prompt"
        ref={input}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={`Try “${IDEAS[idea]}”`}
        autoComplete="off"
        className="min-w-0 flex-1 truncate bg-transparent py-2.5 text-sm text-white outline-none placeholder:text-white/65 focus-visible:outline-none sm:text-[15px]"
      />
      <button
        disabled={starting}
        className="group flex shrink-0 items-center gap-1.5 rounded-full bg-coral px-4 py-2.5 text-sm font-semibold text-white shadow-[0_8px_24px_-8px_rgb(255_106_74/0.7)] transition hover:bg-coral-deep disabled:opacity-60 sm:px-5"
      >
        {starting
          ? <span className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
          : <>Plan my trip <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" /></>}
      </button>
    </form>
  );
}
