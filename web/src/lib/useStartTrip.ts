"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { createTrip } from "./api";

// Creates a trip and opens the workspace. The first prompt is handed over via sessionStorage
// (not the URL) so trip details never land in history or logs.
export function useStartTrip() {
  const router = useRouter();
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start(prompt?: string) {
    setStarting(true);
    setError(null);
    try {
      const id = await createTrip();
      if (prompt) {
        try { sessionStorage.setItem(`pending:${id}`, prompt); } catch {}
      }
      router.push(`/plan?id=${id}`);
    } catch (e) {
      setError((e as Error).message);
      setStarting(false);
    }
  }
  return { start, starting, error };
}
