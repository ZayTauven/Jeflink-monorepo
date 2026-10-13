"use client";

import { useContext, type ReactNode } from "react";
import { useFormStatus } from "react-dom";

import { Sending } from "./action-form";

/**
 * Bouton d'envoi : pendant l'envoi, un spinner remplace le libellé (sans changer la largeur
 * du bouton) et le bouton est désactivé (pas de double action).
 */
export function Submit({
  children,
  className = "ax-btn ax-btn--primary",
}: {
  children: ReactNode;
  className?: string;
}) {
  const status = useFormStatus();
  const sending = useContext(Sending);
  const pending = status.pending || sending;
  return (
    <button
      type="submit"
      className={`${className}${pending ? " jf-busy" : ""}`}
      disabled={pending}
      aria-busy={pending}
    >
      <span className="jf-busy__label">{children}</span>
      {pending && (
        <span className="ax-spinner ax-spinner--sm jf-busy__spinner" aria-hidden="true">
          <span className="ax-spinner__glyph" />
        </span>
      )}
    </button>
  );
}
