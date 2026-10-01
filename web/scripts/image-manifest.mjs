// Lists the photos in public/images so the app only requests files that exist (no 404s).
// Runs automatically before `npm run dev` and `npm run build`.
import { readdirSync, writeFileSync, existsSync } from "node:fs";
import { join, parse } from "node:path";

const root = new URL("../public/images/", import.meta.url).pathname;
const exts = new Set([".jpg", ".jpeg", ".png", ".webp", ".avif"]);
const manifest = {};

function walk(dir, rel = "") {
  if (!existsSync(dir)) return;
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (e.isDirectory()) walk(join(dir, e.name), `${rel}${e.name}/`);
    else if (exts.has(parse(e.name).ext.toLowerCase())) manifest[`${rel}${parse(e.name).name}`] = `/images/${rel}${e.name}`;
  }
}
walk(root);
writeFileSync(new URL("../src/lib/image-manifest.json", import.meta.url), JSON.stringify(manifest, null, 2) + "\n");
console.log(`image manifest: ${Object.keys(manifest).length} photo(s)`);
