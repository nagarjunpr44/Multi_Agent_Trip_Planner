// Image slots. Add photos without touching components — drop files into web/public/images/:
//   hero.jpg                       landing hero (wide, ~2400px)
//   destinations/<slug>.jpg        destination cards + trip covers, e.g. lisbon.jpg, mexico-city.webp
// Then restart `npm run dev` (or rebuild). Missing photos fall back to a gradient placeholder.
// To use a remote photo instead, add it to OVERRIDES (key = slug).
import manifest from "./image-manifest.json";

const files = manifest as Record<string, string>;

const OVERRIDES: Record<string, string> = {
  // lisbon: "https://images.example.com/lisbon.jpg",
};

export const HERO_IMAGE = files["hero"];

export const slug = (s: string) =>
  s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().split(",")[0].trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

export const destinationImage = (name?: string) => {
  if (!name) return undefined;
  const key = slug(name);
  return OVERRIDES[key] ?? files[`destinations/${key}`];
};

// Placeholder palettes: [sky, mid, ground]. Picked deterministically from the label.
const TONES: [string, string, string][] = [
  ["#ffd3a5", "#fd6f4f", "#5b1f2c"], // sunset
  ["#c8ecf0", "#3f9aa8", "#0e2e3c"], // lagoon
  ["#f9e2c6", "#d48c5c", "#4d2a1c"], // desert
  ["#e6dcf5", "#9878c2", "#2c1f45"], // dusk
  ["#d6efcf", "#5b9b6e", "#1d3a2a"], // forest
  ["#fde7b0", "#e5a83a", "#5a3410"], // gold
];
export function tone(label = "") {
  if (label === "hero") return TONES[0];
  let h = 0;
  for (const c of label) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return TONES[h % TONES.length];
}
