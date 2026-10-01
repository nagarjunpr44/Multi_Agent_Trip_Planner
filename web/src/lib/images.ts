// Image slots. Add photos without touching components — drop files into web/public/images/:
//   destinations/<slug>.jpg        destination cards + trip covers, e.g. lisbon.jpg, mexico-city.webp
// Then restart `npm run dev` (or rebuild). Missing photos fall back to a gradient placeholder.
// To use a remote photo instead, add it to OVERRIDES (key = slug).
import manifest from "./image-manifest.json";
import type { Trip } from "./types";

const files = manifest as Record<string, string>;

const OVERRIDES: Record<string, string> = {
  // lisbon: "https://images.example.com/lisbon.jpg",
};

export const slug = (s: string) =>
  s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().split(",")[0].trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

export const destinationImage = (name?: string) => {
  if (!name) return undefined;
  const key = slug(name);
  return OVERRIDES[key] ?? files[`destinations/${key}`];
};

// Best real image for a trip: a photo you added for the destination, else the provider's photo
// of the first stop (or the hotel). Undefined → callers fall back to a placeholder or scene.
export function tripCover(trip?: Trip) {
  if (!trip) return undefined;
  const stopPhoto = trip.days.flatMap((d) => d.stops).find((s) => s.place.photo_url)?.place.photo_url;
  return destinationImage(trip.destinations[0]) ?? (stopPhoto || trip.hotel?.photo_url || undefined);
}

// Placeholder palettes: [sky, mid, ground]. Picked deterministically from the label.
const TONES: [string, string, string][] = [
  ["#f6a97e", "#c4475a", "#2a1020"], // sunset
  ["#7fb8c9", "#2c5d72", "#0a1a24"], // lagoon
  ["#e9b48a", "#9a5134", "#26130c"], // desert
  ["#b9a3e0", "#5e4596", "#160f2a"], // dusk
  ["#a8cfa5", "#3c6b4d", "#0d1d15"], // forest
  ["#f4c977", "#b0702a", "#2c1806"], // gold
];
export function tone(label = "") {
  let h = 0;
  for (const c of label) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return TONES[h % TONES.length];
}
