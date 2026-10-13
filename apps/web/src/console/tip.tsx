"use client";

/**
 * Infobulle d'un bouton-icône (`.ax-tooltip--inverse` de vireo) : au survol et au clavier,
 * Échap la ferme. Posée sur <body> en position fixe, pour ne pas être coupée par le menu
 * latéral (qui défile). Le bouton garde son `aria-label` : la bulle ne fait que le montrer.
 * `collapsedOnly` : seulement quand le menu latéral est replié (icônes seules).
 */
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

type Side = "bottom" | "end";

export function Tip({
  label,
  side = "bottom",
  collapsedOnly = false,
  block = false,
  children,
}: {
  label: string;
  side?: Side;
  collapsedOnly?: boolean;
  block?: boolean;
  children: ReactNode;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const bubble = useRef<HTMLSpanElement>(null);
  const [at, setAt] = useState<{ x: number; y: number } | null>(null);

  // Bulle centrée sous le bouton, ramenée dans l'écran si elle déborde (bouton au bord).
  useLayoutEffect(() => {
    const b = bubble.current;
    if (!b || !at) return;
    const r = b.getBoundingClientRect();
    const shift = Math.max(8 - r.left, 0) - Math.max(r.right - (window.innerWidth - 8), 0);
    if (shift) b.style.left = `${at.x + shift}px`;
  }, [at]);

  function show() {
    const el = ref.current;
    if (!el) return;
    // Menu replié (bureau seulement : sur téléphone, le tiroir affiche les libellés).
    if (
      collapsedOnly &&
      (!document.documentElement.hasAttribute("data-ax-collapsed") ||
        !window.matchMedia("(min-width: 768px)").matches)
    ) {
      return;
    }
    const r = el.getBoundingClientRect();
    if (side === "end") {
      setAt({ x: r.right + 10, y: r.top + r.height / 2 });
      return;
    }
    setAt({ x: r.left + r.width / 2, y: r.bottom + 8 });
  }

  useEffect(() => {
    if (!at) return;
    const hide = () => setAt(null);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") hide();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("scroll", hide, true);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", hide, true);
    };
  }, [at]);

  return (
    <span
      ref={ref}
      className={`jf-tip${block ? " jf-tip--block" : ""}`}
      onMouseEnter={show}
      onMouseLeave={() => setAt(null)}
      onFocus={show}
      onBlur={() => setAt(null)}
      onClick={() => setAt(null)}
    >
      {children}
      {at &&
        createPortal(
          <span
            ref={bubble}
            className={`ax-tooltip ax-tooltip--inverse jf-tip__bubble jf-tip__bubble--${side}`}
            style={{ left: at.x, top: at.y }}
            aria-hidden="true"
          >
            {label}
          </span>,
          document.body,
        )}
    </span>
  );
}
