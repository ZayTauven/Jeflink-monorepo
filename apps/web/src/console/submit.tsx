"use client";

import type { ReactNode } from "react";
import { useFormStatus } from "react-dom";

/** Bouton d'envoi désactivé pendant l'envoi (pas de double action). */
export function Submit({
  children,
  className = "ax-btn ax-btn--primary",
}: {
  children: ReactNode;
  className?: string;
}) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" className={className} disabled={pending} aria-busy={pending}>
      {pending ? "Envoi…" : children}
    </button>
  );
}
