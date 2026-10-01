"use client";

import { useEffect, useRef } from "react";
import { registerKeyPrompt } from "@/lib/api";

// Asks for the API key when the server answers 401. Mounted once in the root layout.
export function AuthGate() {
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const resolver = useRef<((v: string | null) => void) | null>(null);

  useEffect(() => {
    registerKeyPrompt(
      () =>
        new Promise((resolve) => {
          resolver.current = resolve;
          dialog.current?.showModal();
          input.current?.focus();
        }),
    );
    return () => registerKeyPrompt(null);
  }, []);

  const close = (value: string | null) => {
    resolver.current?.(value);
    resolver.current = null;
    dialog.current?.close();
  };

  return (
    <dialog
      ref={dialog}
      onCancel={() => close(null)}
      className="glass-panel m-auto w-[min(420px,92vw)] rounded-3xl p-7 text-white backdrop:bg-black/50 backdrop:backdrop-blur-sm"
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          close(input.current?.value.trim() || null);
        }}
      >
        <h2 className="font-display text-3xl">API key needed</h2>
        <p className="mt-2 text-sm text-mist">This planner is protected. Enter its API key to continue.</p>
        <input ref={input} type="password" autoComplete="off" aria-label="API key"
          className="mt-5 w-full rounded-xl border border-rim bg-white/5 px-4 py-3 outline-none focus:border-white/40" />
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={() => close(null)} className="rounded-full px-5 py-2.5 font-semibold hover:bg-white/10">Cancel</button>
          <button className="rounded-full bg-coral px-5 py-2.5 font-semibold text-white hover:bg-coral-deep">Unlock</button>
        </div>
      </form>
    </dialog>
  );
}
