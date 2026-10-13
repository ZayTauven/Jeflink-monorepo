"use client";

/**
 * Barre d'enregistrement d'un long formulaire (Réglages, Commissions), collée en bas de
 * l'écran. Dès qu'un champ change : « Modifications non enregistrées », un bouton « Annuler »
 * (remet les valeurs enregistrées) et une alerte du navigateur si l'on quitte la page.
 * À placer dans le formulaire, avec son bouton `Submit` en enfant.
 */
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

export function SaveBar({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [dirty, setDirty] = useState(false);
  const params = useSearchParams();

  useEffect(() => {
    const form = ref.current?.closest("form");
    if (!form) return;
    const mark = () => setDirty(true);
    const clear = () => setDirty(false);
    form.addEventListener("input", mark);
    form.addEventListener("change", mark);
    form.addEventListener("reset", clear);
    return () => {
      form.removeEventListener("input", mark);
      form.removeEventListener("change", mark);
      form.removeEventListener("reset", clear);
    };
  }, []);

  // Enregistré : l'action revient sur la page avec un message.
  useEffect(() => {
    if (params.get("ok")) setDirty(false);
  }, [params]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  return (
    <div ref={ref} className={`jf-sticky-save${dirty ? " is-dirty" : ""}`}>
      <p className="jf-sticky-save__note" role="status">
        {dirty && "Modifications non enregistrées"}
      </p>
      {dirty && (
        <button type="reset" className="ax-btn ax-btn--ghost">
          Annuler
        </button>
      )}
      {children}
    </div>
  );
}
