# Wayfarer web UI

Next.js (App Router) + Tailwind + Motion + Leaflet. Built as a **static export** that the
FastAPI app serves from `web/out`, so production is still one Python process.

```bash
npm install
npm run dev     # http://localhost:3000, proxies /trips/* to the API (API_URL, default http://127.0.0.1:8000)
npm run build   # writes out/; restart nothing, FastAPI serves it at http://127.0.0.1:8000
npm run lint
```

## Pages

- `/` landing: window-seat video hero (crossfading scenes behind a train-window overlay, trip
  prompt, scene switcher), destination carousel, your trips, how it works.
- `/plan/?id=<trip>` workspace: chat | itinerary | map. Below 1280px the itinerary and map
  share a column (toggle); below 1024px a bottom tab bar switches Chat / Itinerary / Map.

## Photos

Every image is an optional slot with a designed gradient fallback. Drop files into
`public/images/` and restart `npm run dev` (or rebuild):

| File | Used for |
| --- | --- |
| `destinations/<slug>.jpg` | destination cards and trip covers, e.g. `lisbon.jpg`, `mexico-city.webp` |

The slug is the lowercased destination with accents and punctuation turned into dashes
(`Reykjavík` → `reykjavik`). `.jpg/.jpeg/.png/.webp/.avif` all work. For a remote URL, add it to
`OVERRIDES` in `src/lib/images.ts`. A build step (`scripts/image-manifest.mjs`) lists the files,
so missing photos never cause 404s.

## Hero scenes

`src/components/landing/Hero.tsx` lists the scenes (`SCENES`): video URL, label, and whether
the scene is bright enough to need dark text. Posters in `public/images/hero/scene-N.webp` are each
video's first frame, shown until the video loads (and instead of it with reduced motion or data
saver). The MP4s currently stream from an external CDN; for production, put them in
`public/videos/` (or your own CDN) and update `src`. `window.webp` is the train-window overlay.

## Map tiles

Defaults to OpenStreetMap tiles, which are fine for development and light use. For production
traffic set `NEXT_PUBLIC_MAP_TILES` (and `NEXT_PUBLIC_MAP_ATTRIBUTION`) at build time to a tile
provider such as MapTiler or Stadia.

## Code map

- `src/lib/api.ts` fetch + SSE client (API key prompt via `components/AuthGate.tsx`)
- `src/lib/types.ts` mirrors `trip_planner/trip/models.py` and the stream event schema
- `src/components/plan/useTrip.ts` loads a trip and folds stream events into chat messages
- `src/components/plan/{ChatPanel,Itinerary,TripMap}.tsx` the three workspace panes
