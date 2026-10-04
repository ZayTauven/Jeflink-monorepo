"use client";

// Appel d'une Server Action sur la réservation, avec l'état commun des panneaux : en cours, erreur
// décrite, rafraîchissement de la page au succès (jamais de `redirect`, spec 001).
import { refreshWebSession } from "@jeflink/api-client/web";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import type { RequestError } from "@/lib/requests/errors";
import { type ActionResult, callAction } from "@/lib/requests/result";

export function useBookingAction() {
  const router = useRouter();
  const [, startRefresh] = useTransition();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<RequestError | null>(null);

  /** Vrai si l'action a réussi. Session finie : retour à la connexion, puis à cette page. */
  async function run(call: () => Promise<ActionResult<{ id: string }>>): Promise<boolean> {
    if (pending) return false;
    setPending(true);
    setError(null);
    const result = await callAction(call, refreshWebSession);
    if (result.ok) {
      startRefresh(() => router.refresh());
      setPending(false);
      return true;
    }
    if (result.error.login) {
      window.location.assign(`/connexion?next=${encodeURIComponent(window.location.pathname)}`);
      return false;
    }
    setPending(false);
    setError(result.error);
    return false;
  }

  return { pending, error, clearError: () => setError(null), run };
}
