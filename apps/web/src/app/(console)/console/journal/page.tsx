import type { Metadata } from "next";
import Link from "next/link";

import { AuditCard, CardGrid } from "@/console/cards";
import { consoleGet, type Query } from "@/console/data";
import { Pager } from "@/console/kit";
import type { AuditRow, Page } from "@/console/types";
import { PageHead } from "@/console/ui";

export const metadata: Metadata = { title: "Journal des actions" };

const BASE = "/console/journal";

const TARGETS: Record<string, string> = {
  pro: "le pro",
  client: "le client",
  request: "la demande",
  review: "l'avis",
  contact: "le message",
  dispute: "le litige",
};

const ACTIONS: [string, string][] = [
  ["pro.verify", "Pro vérifié"],
  ["pro.reject", "Vérification refusée"],
  ["user.suspend", "Compte suspendu"],
  ["user.reactivate", "Compte réactivé"],
  ["request.cancel", "Demande annulée par l'équipe"],
  ["request.note", "Note interne modifiée"],
  ["review.hide", "Avis masqué"],
  ["review.show", "Avis rétabli"],
  ["contact.handle", "Message traité"],
  ["contact.reopen", "Message rouvert"],
  ["dispute.open", "Litige ouvert"],
  ["dispute.update", "Litige mis à jour"],
];

export default async function AuditPage({ searchParams }: { searchParams: Promise<Query> }) {
  const params = await searchParams;
  const data = await consoleGet<Page<AuditRow>>(BASE, "audit/", {
    action: params.action,
    target_type: params.cible,
    target_id: params.id,
    days: params.jours,
    page: params.page,
  });

  return (
    <>
      <PageHead
        title="Journal des actions"
        subtitle="Chaque action de l'équipe dans la console : qui, quoi, sur quelle fiche, quand. Le journal ne se modifie pas."
      />
      {params.cible && params.id && (
        <p className="jf-muted mb-4" role="status">
          Seules les actions sur {TARGETS[params.cible] ?? "une fiche"} n°&nbsp;{params.id} sont
          affichées.{" "}
          <Link href={BASE} className="jf-link">
            Voir tout le journal
          </Link>
        </p>
      )}
      <form className="jf-filters" method="get" action={BASE}>
        {params.cible && <input type="hidden" name="cible" value={params.cible} />}
        {params.id && <input type="hidden" name="id" value={params.id} />}
        <div className="ax-field">
          <label className="ax-field__label" htmlFor="action">
            Action
          </label>
          <select
            id="action"
            name="action"
            className="ax-select"
            defaultValue={params.action ?? ""}
          >
            <option value="">Toutes</option>
            {ACTIONS.map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </div>
        <div className="ax-field">
          <label className="ax-field__label" htmlFor="jours">
            Période
          </label>
          <select id="jours" name="jours" className="ax-select" defaultValue={params.jours ?? ""}>
            <option value="">Depuis le début</option>
            <option value="1">24 dernières heures</option>
            <option value="7">7 derniers jours</option>
            <option value="30">30 derniers jours</option>
          </select>
        </div>
        <div className="jf-filters__actions">
          <button type="submit" className="ax-btn ax-btn--primary">
            Filtrer
          </button>
          <Link href={BASE} className="ax-btn ax-btn--ghost">
            Effacer
          </Link>
        </div>
      </form>
      <CardGrid empty="Aucune action enregistrée pour ces filtres.">
        {data.results.map((row) => (
          <AuditCard key={row.id} row={row} />
        ))}
      </CardGrid>
      <Pager count={data.count} base={BASE} params={params} />
    </>
  );
}
