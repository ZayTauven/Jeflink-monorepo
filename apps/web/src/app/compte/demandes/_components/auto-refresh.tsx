"use client";

// Actualisation automatique du suivi (spec 004, web 1) : toutes les 60 s, seulement quand
// l'onglet est visible et la mission en cours. La règle vit dans `lib/bookings/auto-refresh.ts`.
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { createAutoRefresh } from "@/lib/bookings/auto-refresh";

export function AutoRefresh({ active }: { active: boolean }) {
  const router = useRouter();
  useEffect(() => {
    const refresh = createAutoRefresh({
      tick: () => router.refresh(),
      isVisible: () => document.visibilityState === "visible",
      isOnline: () => navigator.onLine,
      now: () => Date.now(),
      setTimer: (run, ms) => window.setInterval(run, ms),
      clearTimer: (handle) => window.clearInterval(handle as number),
    });
    const sync = () => refresh.sync(active);
    sync();
    document.addEventListener("visibilitychange", sync);
    return () => {
      document.removeEventListener("visibilitychange", sync);
      refresh.stop();
    };
  }, [active, router]);
  return null;
}
