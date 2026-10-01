import type { StreamEvent, ThreadData, TripSummary } from "./types";

// ── API key (only needed when the server sets APP_API_KEY) ──────────────────
// AuthGate registers a prompt; parallel 401s share one prompt.
let askForKey: (() => Promise<string | null>) | null = null;
let pendingKey: Promise<string | null> | null = null;
export const registerKeyPrompt = (fn: typeof askForKey) => { askForKey = fn; };

const getKey = () => { try { return localStorage.getItem("apiKey"); } catch { return null; } };

export async function api(path: string, init: RequestInit = {}): Promise<Response> {
  const key = getKey();
  const resp = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(key ? { Authorization: `Bearer ${key}` } : {}) },
  });
  if (resp.status === 401 && askForKey) {
    pendingKey ??= askForKey().finally(() => setTimeout(() => (pendingKey = null)));
    const entered = await pendingKey;
    if (entered) {
      try { localStorage.setItem("apiKey", entered); } catch {}
      return api(path, init);
    }
  }
  if (!resp.ok) {
    let detail = resp.statusText;
    try { detail = (await resp.json()).detail || detail; } catch {}
    throw new Error(`${resp.status}: ${detail}`);
  }
  return resp;
}

export const listTrips = async (): Promise<TripSummary[]> => (await api("/trips")).json();
export const createTrip = async (): Promise<string> => (await (await api("/trips", { method: "POST" })).json()).id;
export const getTrip = async (id: string): Promise<ThreadData> => (await api(`/trips/${id}`)).json();
export const deleteTrip = (id: string) => api(`/trips/${id}`, { method: "DELETE" });

// POST and read the SSE body (EventSource can't POST).
export async function stream(path: string, body: unknown, onEvent: (e: StreamEvent) => void) {
  const resp = await api(path, { method: "POST", body: JSON.stringify(body) });
  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let cut;
    while ((cut = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, cut);
      buf = buf.slice(cut + 2);
      if (chunk.startsWith("data: ")) onEvent(JSON.parse(chunk.slice(6)));
    }
  }
}
