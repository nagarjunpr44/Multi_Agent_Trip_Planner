"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ArrowUp, Check, ChevronDown, Sparkles, X } from "lucide-react";
import clsx from "clsx";
import { Markdown } from "@/components/Markdown";
import { usd } from "@/lib/format";
import type { Approval, Trip } from "@/lib/types";
import type { Msg, Tool } from "./useTrip";

const appear = { initial: { opacity: 0, y: 12 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.35, ease: [0.16, 1, 0.3, 1] as const } };

export function ChatPanel({ msgs, busy, trip, onSend, onAnswer, className }: {
  msgs: Msg[];
  busy: boolean;
  trip?: Trip;
  onSend: (text: string) => void;
  onAnswer: (approved: boolean, note: string) => void;
  className?: string;
}) {
  const scroller = useRef<HTMLDivElement>(null);
  const pinned = useRef(true); // follow new content only while the user is at the bottom

  useEffect(() => {
    const el = scroller.current;
    if (el && pinned.current) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [msgs, busy]);

  const last = msgs.at(-1);
  const thinking = busy && !(last?.kind === "assistant" && last.streaming);

  return (
    <section aria-label="Chat with the planner" className={clsx("min-h-0 flex-col border-line bg-white lg:border-r", className)}>
      <div className="flex items-center gap-3 border-b border-line px-5 py-3.5">
        <Avatar />
        <div className="min-w-0">
          <p className="font-semibold leading-tight">Wayfarer planner</p>
          <p className="flex items-center gap-1.5 text-xs text-ink-soft">
            <span className={clsx("size-1.5 rounded-full", busy ? "animate-pulse bg-coral" : "bg-lagoon")} />
            {busy ? "Working on your trip…" : "Ready"}
          </p>
        </div>
      </div>

      <div
        ref={scroller}
        onScroll={(e) => { const el = e.currentTarget; pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80; }}
        role="log" aria-live="polite"
        className="pane flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-5 py-6"
      >
        {msgs.length === 0 && !busy && (trip?.days.length ? <Resume /> : <Welcome onSend={onSend} />)}
        {msgs.map((m, i) => <Message key={i} m={m} busy={busy} onAnswer={onAnswer} />)}
        <AnimatePresence>{thinking && <Thinking />}</AnimatePresence>
      </div>

      <Composer busy={busy} trip={trip} onSend={onSend} />
    </section>
  );
}

function Avatar({ small }: { small?: boolean }) {
  return (
    <span className={clsx("grid shrink-0 place-items-center rounded-full bg-ink text-white", small ? "size-7" : "size-9")}>
      <Sparkles className={small ? "size-3.5" : "size-4"} />
    </span>
  );
}

function Message({ m, busy, onAnswer }: { m: Msg; busy: boolean; onAnswer: (a: boolean, n: string) => void }) {
  switch (m.kind) {
    case "user":
      return (
        <motion.div {...appear} className="ml-auto max-w-[85%] whitespace-pre-wrap rounded-[20px] rounded-br-md bg-ink px-4 py-2.5 text-[15px] text-white">
          {m.text}
        </motion.div>
      );
    case "assistant":
      return (
        <motion.div {...appear} className="flex max-w-full gap-3">
          <Avatar small />
          <div className={clsx("min-w-0 text-[15px] leading-relaxed", m.streaming && "[&>*:last-child]:after:ml-0.5 [&>*:last-child]:after:inline-block [&>*:last-child]:after:h-4 [&>*:last-child]:after:w-1.5 [&>*:last-child]:after:animate-pulse [&>*:last-child]:after:bg-coral [&>*:last-child]:after:align-[-2px] [&>*:last-child]:after:content-['']")}>
            <Markdown text={m.text} />
          </div>
        </motion.div>
      );
    case "tools":
      return <ToolGroup items={m.items} />;
    case "approval":
      return <ApprovalCard approval={m.approval} disabled={busy} onAnswer={onAnswer} />;
    case "error":
      return (
        <motion.div {...appear} role="alert" className="rounded-2xl border border-coral/30 bg-coral/5 px-4 py-3 text-sm text-coral-deep">
          Something went wrong: {m.text}
        </motion.div>
      );
  }
}

// Live while running; collapses into a one-line summary when every tool is done.
function ToolGroup({ items }: { items: Tool[] }) {
  const allDone = items.every((t) => t.done);
  const [open, setOpen] = useState(false);
  const expanded = !allDone || open;
  const secs = items.reduce((s, t) => s + (t.ms ?? 0), 0) / 1000;
  const failed = items.filter((t) => t.ok === false).length;

  return (
    <motion.div {...appear} className="ml-10 overflow-hidden rounded-2xl border border-line bg-sand/60">
      <button onClick={() => setOpen((o) => !o)} disabled={!allDone} aria-expanded={expanded}
        className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-[13px] font-medium text-ink-soft">
        {allDone
          ? <span className="grid size-4 place-items-center rounded-full bg-lagoon text-white"><Check className="size-3" strokeWidth={3} /></span>
          : <span className="size-4 animate-spin rounded-full border-2 border-line border-t-coral" />}
        <span className="flex-1">
          {allDone ? `Checked ${items.length} source${items.length > 1 ? "s" : ""}${secs >= 1 ? ` in ${secs.toFixed(1)}s` : ""}${failed ? ` · ${failed} failed` : ""}` : items.findLast((t) => !t.done)?.label ?? "Working…"}
        </span>
        {allDone && <ChevronDown className={clsx("size-4 transition-transform", open && "rotate-180")} />}
      </button>
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.ul initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }} className="space-y-1.5 px-4 pb-3 font-mono text-[12px] text-ink-soft">
            {items.map((t, i) => (
              <motion.li key={i} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} className={clsx("flex items-center gap-2", t.ok === false && "text-coral-deep")}>
                {t.done
                  ? t.ok ? <Check className="size-3.5 text-lagoon" strokeWidth={3} /> : <X className="size-3.5" strokeWidth={3} />
                  : <span className="size-3.5 animate-spin rounded-full border-[1.5px] border-line border-t-coral" />}
                <span className="truncate">{t.label}{t.ok === false && t.summary ? `: ${t.summary}` : ""}</span>
                {t.ms != null && t.ms >= 1000 && <span className="ml-auto shrink-0 opacity-60">{(t.ms / 1000).toFixed(1)}s</span>}
              </motion.li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function ApprovalCard({ approval, disabled, onAnswer }: { approval: Approval; disabled: boolean; onAnswer: (a: boolean, n: string) => void }) {
  const [note, setNote] = useState("");
  const [asking, setAsking] = useState(false);
  return (
    <motion.div initial={{ opacity: 0, y: 24, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ type: "spring", bounce: 0.3, duration: 0.7 }}
      className="relative overflow-hidden rounded-[24px] bg-ink p-5 text-white shadow-lift">
      <div aria-hidden className="absolute -right-10 -top-10 size-40 rounded-full bg-coral/30 blur-3xl" />
      <p className="text-xs font-bold uppercase tracking-[0.16em] text-coral">Ready for review</p>
      <p className="mt-2 font-display text-3xl leading-tight">Your trip is ready to book</p>
      <div className="mt-2 text-sm text-white/75"><Markdown text={approval.summary} /></div>
      <p className="mt-4 font-display text-4xl">{usd(approval.total_usd)}<span className="ml-2 font-sans text-sm text-white/60">estimated total</span></p>
      {asking && (
        <textarea autoFocus value={note} onChange={(e) => setNote(e.target.value)} rows={2} placeholder="What should change?"
          className="mt-4 w-full resize-none rounded-xl bg-white/10 px-3 py-2.5 text-sm outline-none placeholder:text-white/50 focus:bg-white/15" />
      )}
      <div className="mt-4 flex gap-2">
        <button disabled={disabled} onClick={() => (asking && note.trim() ? onAnswer(false, note.trim()) : setAsking(true))}
          className="flex-1 rounded-full border border-white/25 px-4 py-2.5 text-sm font-semibold transition hover:bg-white/10 disabled:opacity-50">
          {asking ? "Send changes" : "Request changes"}
        </button>
        <button disabled={disabled} onClick={() => onAnswer(true, "")}
          className="flex-1 rounded-full bg-coral px-4 py-2.5 text-sm font-semibold transition hover:bg-coral-deep disabled:opacity-50">
          Approve plan
        </button>
      </div>
    </motion.div>
  );
}

function Thinking() {
  return (
    <motion.div {...appear} exit={{ opacity: 0 }} className="flex items-center gap-3" aria-label="Planner is thinking">
      <Avatar small />
      <span className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <motion.span key={i} className="size-2 rounded-full bg-ink-soft" animate={{ y: [0, -5, 0], opacity: [0.4, 1, 0.4] }} transition={{ duration: 1, repeat: Infinity, delay: i * 0.15 }} />
        ))}
      </span>
    </motion.div>
  );
}

function Resume() {
  return (
    <motion.div {...appear} className="m-auto max-w-xs py-10 text-center">
      <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-lagoon/10 text-lagoon"><Sparkles className="size-6" /></span>
      <p className="mt-4 font-display text-3xl">Welcome back</p>
      <p className="mt-2 text-sm text-ink-soft">Your plan is on the right. Ask me to change anything: swap a stop, slow a day down, find a cheaper hotel.</p>
    </motion.div>
  );
}

const STARTERS = ["5 days in Lisbon in May, 2 people, ~$3000", "A relaxed week in Kyoto in April", "Weekend in Paris for a birthday"];

function Welcome({ onSend }: { onSend: (t: string) => void }) {
  return (
    <motion.div {...appear} className="m-auto max-w-xs py-10 text-center">
      <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-coral/10 text-coral"><Sparkles className="size-6" /></span>
      <p className="mt-4 font-display text-3xl">Where to?</p>
      <p className="mt-2 text-sm text-ink-soft">Tell me the destination, dates, who&apos;s coming and a rough budget.</p>
      <div className="mt-5 flex flex-col gap-2">
        {STARTERS.map((s) => (
          <button key={s} onClick={() => onSend(s)} className="rounded-2xl border border-line px-4 py-2.5 text-left text-sm transition hover:border-ink hover:bg-sand">{s}</button>
        ))}
      </div>
    </motion.div>
  );
}

// Follow-ups that make sense once a plan exists.
function quickReplies(trip?: Trip) {
  if (!trip?.days.length) return [];
  const out = ["Make it more relaxed", "Add a food tour"];
  if (trip.hotel) out.push("Find a cheaper hotel");
  if (trip.days.length > 1) out.push("Swap day 1 and day 2");
  return out;
}

function Composer({ busy, trip, onSend }: { busy: boolean; trip?: Trip; onSend: (t: string) => void }) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, [text]);

  const submit = () => {
    const t = text.trim();
    if (!t || busy) return;
    setText("");
    onSend(t);
  };
  const chips = quickReplies(trip);

  return (
    <div className="border-t border-line bg-white px-4 pb-4 pt-3">
      {chips.length > 0 && (
        <div className="mb-2.5 flex gap-2 overflow-x-auto [scrollbar-width:none]">
          {chips.map((c) => (
            <button key={c} disabled={busy} onClick={() => onSend(c)}
              className="shrink-0 rounded-full border border-line px-3 py-1.5 text-xs font-medium text-ink-soft transition hover:border-ink hover:text-ink disabled:opacity-50">{c}</button>
          ))}
        </div>
      )}
      <form onSubmit={(e) => { e.preventDefault(); submit(); }}
        className="flex items-end gap-2 rounded-[22px] border border-line bg-sand/50 p-1.5 pl-4 transition focus-within:border-ink focus-within:bg-white">
        <label htmlFor="composer" className="sr-only">Message</label>
        <textarea id="composer" ref={ref} rows={1} value={text} onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); } }}
          placeholder={trip?.days.length ? "Ask for changes…" : "Describe your trip…"}
          className="max-h-40 flex-1 resize-none bg-transparent py-2 text-[15px] outline-none placeholder:text-ink-soft/70" />
        <button aria-label="Send" disabled={busy || !text.trim()}
          className="grid size-10 shrink-0 place-items-center rounded-full bg-coral text-white transition hover:bg-coral-deep disabled:bg-line disabled:text-ink-soft">
          <ArrowUp className="size-5" />
        </button>
      </form>
    </div>
  );
}
