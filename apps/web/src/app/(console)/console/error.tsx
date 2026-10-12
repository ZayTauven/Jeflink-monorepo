"use client";

import Link from "next/link";

/** Erreur dans une rubrique (souvent : l'API n'est pas lancée). Le menu reste utilisable. */
export default function ConsoleError({ reset }: { error: Error; reset: () => void }) {
  return (
    <section className="ax-card jf-soon-hero" role="alert">
      <div className="ax-card__body">
        <p className="ax-card__eyebrow">Rubrique indisponible</p>
        <h1 className="ax-card__title">Les données n&apos;ont pas pu être chargées.</h1>
        <p className="jf-prose">
          Le service ne répond pas. Réessayez dans un instant ; si cela continue, prévenez
          l&apos;équipe technique.
        </p>
        <div className="jf-inline">
          <button type="button" className="ax-btn ax-btn--primary" onClick={reset}>
            Réessayer
          </button>
          <Link href="/console" className="ax-btn ax-btn--ghost">
            Tableau de bord
          </Link>
        </div>
      </div>
    </section>
  );
}
