// Bandeau défilant des métiers (Crafto section 6, refait en CSS : ni Swiper ni anime.js).
// - Noms des métiers (données) en Funnel Display, copie doublée en `aria-hidden` pour la boucle.
// - Le défilement ne démarre que si le JS est actif (`@media (scripting: enabled)`) et si le
//   visiteur n'a pas demandé moins de mouvement ; sinon, une liste statique, tout est lisible.
// - Pause : arrêt au survol et au focus (CSS), et bouton « Mettre en pause » (îlot client, WCAG 2.2.2).
// - Les métiers restent atteignables en liens ailleurs sur la page : ici, du texte seulement.
import { getTranslations } from "next-intl/server";

import { MarqueeShell } from "./marquee-shell";

export async function Marquee({
  items,
  className = "",
}: {
  /** Noms des métiers, tels que le catalogue les donne. Vide : rien n'est rendu. */
  items: readonly string[];
  className?: string;
}) {
  const names = items.map((item) => item.trim()).filter(Boolean);
  if (names.length === 0) return null;
  const t = await getTranslations("site.marquee");

  const list = (hidden: boolean) => (
    <ul
      className="jf-marquee-copy flex flex-wrap items-center gap-x-8 gap-y-3"
      aria-hidden={hidden ? "true" : undefined}
    >
      {names.map((name, index) => (
        <li
          key={`${name}-${index}`}
          className="flex items-center gap-8 font-display text-5xl leading-none tracking-tight text-ink sm:text-7xl"
        >
          {name}
          <span aria-hidden="true" className="size-3 shrink-0 rounded-pill bg-accent" />
        </li>
      ))}
    </ul>
  );

  return (
    <section aria-label={t("label")} className={className}>
      <MarqueeShell>
        <div className="jf-marquee-track">
          {list(false)}
          {list(true)}
        </div>
      </MarqueeShell>
    </section>
  );
}
