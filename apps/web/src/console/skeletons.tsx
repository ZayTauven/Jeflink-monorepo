/**
 * Trames de chargement des pages de la console (`.ax-skeleton` de vireo), servies par les
 * `loading.tsx` : la page s'affiche aussitôt, son contenu arrive ensuite.
 */
import type { CSSProperties, ReactNode } from "react";

function Bone({ w = "100%", h, round = false }: { w?: string; h: string; round?: boolean }) {
  const style: CSSProperties = { inlineSize: w, blockSize: h };
  return (
    <span
      className={`ax-skeleton ${round ? "ax-skeleton--circle" : "ax-skeleton--rect"} jf-bone`}
      style={style}
    />
  );
}

function Head() {
  return (
    <div className="ax-page-head jf-skel-head">
      <Bone w="min(320px, 70%)" h="2.5rem" />
      <Bone w="min(560px, 90%)" h="1rem" />
    </div>
  );
}

function ItemCard() {
  return (
    <div className="ax-card jf-item" aria-hidden="true">
      <div className="ax-skeleton-row">
        <Bone w="44px" h="44px" round />
        <div className="ax-skeleton-card jf-skel-grow">
          <Bone w="40%" h="0.75rem" />
          <Bone w="75%" h="1.25rem" />
        </div>
      </div>
      <div className="ax-skeleton-card">
        <Bone h="0.875rem" />
        <Bone w="85%" h="0.875rem" />
      </div>
      <div className="jf-item__foot">
        <Bone w="45%" h="2rem" />
        <Bone w="96px" h="2rem" />
      </div>
    </div>
  );
}

function Busy({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="jf-skel" aria-busy="true" role="status">
      <span className="ax-visually-hidden">{label}…</span>
      {children}
    </div>
  );
}

/** Liste en cartes : en-tête, filtres, grille. */
export function ListSkeleton() {
  return (
    <Busy label="Chargement de la page">
      <Head />
      <div className="jf-skel-bar" aria-hidden="true">
        <Bone w="120px" h="2.25rem" />
        <Bone w="160px" h="2.25rem" />
        <Bone w="140px" h="2.25rem" />
      </div>
      <div className="jf-cards">
        {Array.from({ length: 6 }, (_, i) => (
          <ItemCard key={i} />
        ))}
      </div>
    </Busy>
  );
}

/** Fiche : en-tête, colonne principale, colonne latérale. */
export function DetailSkeleton() {
  return (
    <Busy label="Chargement de la fiche">
      <Head />
      <div className="ax-dash-grid" aria-hidden="true">
        <div className="ax-card ax-col--8">
          <div className="ax-card__body ax-skeleton-card">
            <Bone w="30%" h="0.75rem" />
            <Bone w="55%" h="1.5rem" />
            <Bone h="0.875rem" />
            <Bone w="90%" h="0.875rem" />
            <Bone w="70%" h="0.875rem" />
          </div>
        </div>
        <div className="ax-card ax-col--4">
          <div className="ax-card__body ax-skeleton-card">
            <Bone w="40%" h="0.75rem" />
            <Bone w="70%" h="1.5rem" />
            <Bone h="0.875rem" />
            <Bone w="60%" h="0.875rem" />
          </div>
        </div>
        <div className="ax-card ax-col--8">
          <div className="ax-card__body ax-skeleton-card">
            <Bone w="25%" h="0.75rem" />
            <Bone h="6rem" />
          </div>
        </div>
      </div>
    </Busy>
  );
}

/** Tableau de bord : indicateurs, graphique, listes. */
export function DashboardSkeleton() {
  return (
    <Busy label="Chargement du tableau de bord">
      <Head />
      <div className="ax-dash-grid" aria-hidden="true">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="ax-card ax-col--3">
            <div className="ax-card__body ax-skeleton-stat">
              <Bone w="44px" h="44px" round />
              <Bone w="60%" h="0.75rem" />
              <Bone w="50%" h="2rem" />
              <Bone w="80%" h="0.75rem" />
            </div>
          </div>
        ))}
        <div className="ax-card ax-col--8">
          <div className="ax-card__body ax-skeleton-card">
            <Bone w="20%" h="0.75rem" />
            <Bone w="45%" h="1.5rem" />
            <Bone h="16rem" />
          </div>
        </div>
        <div className="ax-card ax-col--4">
          <div className="ax-card__body ax-skeleton-card">
            <Bone w="30%" h="0.75rem" />
            <Bone w="70%" h="1.5rem" />
            {Array.from({ length: 4 }, (_, i) => (
              <Bone key={i} h="2.5rem" />
            ))}
          </div>
        </div>
      </div>
    </Busy>
  );
}
