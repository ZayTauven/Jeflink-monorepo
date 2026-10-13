"use client";

/**
 * Barre de progression fine en haut de l'écran pendant qu'un lien de la console charge
 * sa page (`useLinkStatus`). À placer dans un `<Link>`. Elle n'apparaît qu'après un court
 * délai (CSS) : rien ne clignote quand la page est déjà prête.
 */
import { useLinkStatus } from "next/link";
import { createPortal } from "react-dom";

export function LinkPending() {
  const { pending } = useLinkStatus();
  if (!pending) return null;
  return createPortal(
    <div
      className="ax-progress ax-progress--indeterminate ax-progress--xs jf-topbar"
      aria-hidden="true"
    >
      <div className="ax-progress__track">
        <div className="ax-progress__fill" />
      </div>
    </div>,
    document.body,
  );
}
