"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getTrip, stream } from "@/lib/api";
import type { Approval, Cost, Issue, StreamEvent, Trip } from "@/lib/types";

export type Tool = { name: string; label: string; done?: boolean; ok?: boolean; summary?: string; ms?: number };
export type Msg =
  | { kind: "user"; text: string }
  | { kind: "assistant"; text: string; streaming?: boolean }
  | { kind: "tools"; items: Tool[] }
  | { kind: "approval"; approval: Approval }
  | { kind: "error"; text: string };

export type TripState = { trip: Trip; issues: Issue[]; cost: Cost };

// Folds one stream event into the message list (pure, so React can replay it safely).
function fold(msgs: Msg[], ev: StreamEvent): Msg[] {
  const last = msgs.at(-1);
  const rest = msgs.slice(0, -1);
  const settle = (m: Msg[]) => m.map((x) => (x.kind === "assistant" && x.streaming ? { ...x, streaming: false } : x));
  switch (ev.type) {
    case "text":
      if (last?.kind === "assistant" && last.streaming) return [...rest, { ...last, text: last.text + ev.delta }];
      return [...msgs, { kind: "assistant", text: ev.delta, streaming: true }];
    case "tool_start": {
      const tool = { name: ev.name, label: ev.label };
      if (last?.kind === "tools") return [...rest, { ...last, items: [...last.items, tool] }];
      return [...settle(msgs), { kind: "tools", items: [tool] }];
    }
    case "tool_end": {
      const i = msgs.findLastIndex((m) => m.kind === "tools");
      if (i < 0) return msgs;
      const group = msgs[i] as Extract<Msg, { kind: "tools" }>;
      const j = group.items.findIndex((t) => t.name === ev.name && !t.done);
      if (j < 0) return msgs;
      const items = group.items.with(j, { ...group.items[j], done: true, ok: ev.ok, summary: ev.summary, ms: ev.ms });
      return msgs.with(i, { ...group, items });
    }
    case "approval":
      return [...settle(msgs), { kind: "approval", approval: { summary: ev.summary, total_usd: ev.total_usd } }];
    case "error":
      return [...settle(msgs), { kind: "error", text: ev.message }];
    default:
      return msgs;
  }
}

export function useTrip(id: string | null) {
  const [state, setState] = useState<TripState | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const started = useRef<string | null>(null);

  const run = useCallback(async (path: string, body: unknown) => {
    setBusy(true);
    try {
      await stream(path, body, (ev) => {
        if (ev.type === "trip") setState({ trip: ev.trip, issues: ev.issues, cost: ev.cost });
        else setMsgs((m) => fold(m, ev));
      });
    } catch (e) {
      setMsgs((m) => fold(m, { type: "error", message: (e as Error).message }));
    } finally {
      setMsgs((m) => m.map((x) => (x.kind === "assistant" && x.streaming ? { ...x, streaming: false } : x)));
      setBusy(false);
    }
  }, []);

  const send = useCallback((text: string) => {
    if (!id) return;
    setMsgs((m) => [...m, { kind: "user", text }]);
    return run(`/trips/${id}/messages`, { text });
  }, [id, run]);

  const answer = useCallback((approved: boolean, note: string) => {
    if (!id) return;
    setMsgs((m) => [...m.filter((x) => x.kind !== "approval"), { kind: "user", text: approved ? "Approved ✓" : `Changes: ${note}` }]);
    return run(`/trips/${id}/approval`, { approved, note });
  }, [id, run]);

  useEffect(() => {
    // Guard against React Strict Mode double-invoking effects (would send the first prompt twice).
    if (!id || started.current === id) return;
    started.current = id;
    setState(null);
    setMsgs([]);
    setLoadError(null);
    (async () => {
      try {
        const data = await getTrip(id);
        setState({ trip: data.trip, issues: data.issues, cost: data.cost });
        const history: Msg[] = (data.messages ?? []).map((m) => ({ kind: m.role, text: m.text }));
        if (data.pending_approval) history.push({ kind: "approval", approval: data.pending_approval });
        setMsgs(history);
        let pending: string | null = null;
        try { pending = sessionStorage.getItem(`pending:${id}`); sessionStorage.removeItem(`pending:${id}`); } catch {}
        if (pending) send(pending);
      } catch (e) {
        setLoadError((e as Error).message);
      }
    })();
  }, [id, send]);

  return { state, msgs, busy, loadError, send, answer };
}
