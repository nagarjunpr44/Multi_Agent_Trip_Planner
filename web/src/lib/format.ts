export const usd = (n?: number | null) => (n == null ? "–" : "$" + Math.round(n).toLocaleString("en-US"));
export const hhmm = (t?: string) => (t || "").slice(0, 5);
export const safeUrl = (u?: string) => (u && /^https?:\/\//i.test(u) ? u : undefined);

const asDate = (d: string) => new Date(d.length === 10 ? d + "T00:00" : d);
export const fmtDate = (d?: string | null, opts: Intl.DateTimeFormatOptions = { weekday: "short", month: "short", day: "numeric" }) =>
  d ? asDate(d).toLocaleDateString("en-US", opts) : "";
export const fmtClock = (dt: string) => asDate(dt).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
export const fmtDuration = (min: number) => (min >= 60 ? `${Math.floor(min / 60)}h ${String(min % 60).padStart(2, "0")}m` : `${min}m`);

export function dateRange(start?: string | null, end?: string | null) {
  if (!start) return "Dates to be decided";
  const s = fmtDate(start, { month: "short", day: "numeric" });
  const e = end ? fmtDate(end, { month: "short", day: "numeric", year: "numeric" }) : "?";
  return `${s} – ${e}`;
}

export const nights = (a: string, b: string) => Math.max(1, Math.round((asDate(b).getTime() - asDate(a).getTime()) / 864e5));
