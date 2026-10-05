// Contenu des pages publiques de secours (404 globale, erreur) : jamais un cul-de-sac. Champ
// « Votre quartier », liens vers les métiers (si le cache les a), WhatsApp, accueil. Composant sans
// serveur ni hook : le Server Component `not-found` et la limite d'erreur (Client Component) le
// partagent, avec des libellés déjà traduits.
import type { ReactNode } from "react";

import { buttonClass } from "@/components/ui/button";
import { ChatIcon } from "@/components/ui/icons";
import { SITE_PATHS, tradePath } from "@/lib/site/paths";

import { ZoneSearchFields, type ZoneSearchLabels } from "./zone-search-fields";

export type RecoveryLabels = {
  title: string;
  lead: string;
  tradesTitle: string;
  whatsappLead: string;
  whatsapp: string;
  newTab: string;
  home: string;
  search: ZoneSearchLabels;
};

export function RecoveryPanel({
  labels,
  trades,
  supportHref,
  action,
}: {
  labels: RecoveryLabels;
  trades: readonly { slug: string; name: string }[];
  supportHref: string | null;
  /** Bouton « Réessayer » de la limite d'erreur. */
  action?: ReactNode;
}) {
  return (
    <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6 sm:py-20">
      <h1 className="font-display text-balance text-4xl leading-[1.05] tracking-tight sm:text-6xl">
        {labels.title}
      </h1>
      <p className="mt-4 text-lg text-ink-muted">{labels.lead}</p>
      {action ? <div className="mt-6">{action}</div> : null}

      <ZoneSearchFields labels={labels.search} id="quartier-secours" className="mt-10" />

      {trades.length > 0 ? (
        <section aria-labelledby="secours-metiers" className="mt-10">
          <h2 id="secours-metiers" className="font-display text-2xl tracking-tight">
            {labels.tradesTitle}
          </h2>
          <ul className="mt-3 flex flex-wrap gap-3">
            {trades.map((trade) => (
              <li key={trade.slug}>
                <a href={tradePath(trade.slug)} className={buttonClass("secondary")}>
                  {trade.name}
                </a>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {supportHref ? (
        <section className="mt-10 flex flex-col items-start gap-3 border-t border-line pt-8">
          <p className="text-base text-ink">{labels.whatsappLead}</p>
          <a
            href={supportHref}
            target="_blank"
            rel="noopener noreferrer"
            className={buttonClass("primary")}
          >
            <ChatIcon className="size-5" />
            {labels.whatsapp}
            <span className="sr-only"> {labels.newTab}</span>
          </a>
        </section>
      ) : null}

      <p className="mt-8">
        <a href={SITE_PATHS.home} className={buttonClass("quiet", "px-0!")}>
          {labels.home}
        </a>
      </p>
    </div>
  );
}
