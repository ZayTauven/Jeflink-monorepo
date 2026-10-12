import type { Metadata } from "next";
import Link from "next/link";

import { targetHref } from "@/console/audit";
import { consoleGet, type Query } from "@/console/data";
import { Pager } from "@/console/kit";
import type { AuditRow, Page } from "@/console/types";
import { Empty, PageHead } from "@/console/ui";
import { formatDate } from "@/lib/format";

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
      <section className="ax-card" aria-label="Journal">
        <div className="ax-card__body">
          {data.results.length === 0 ? (
            <Empty>Aucune action enregistrée pour ces filtres.</Empty>
          ) : (
            <div
              className="ax-table-wrap"
              role="region"
              aria-label="Tableau du journal (défile horizontalement)"
              tabIndex={0}
            >
              <table className="ax-table ax-table--compact">
                <thead>
                  <tr>
                    <th scope="col">Quand</th>
                    <th scope="col">Qui</th>
                    <th scope="col">Action</th>
                    <th scope="col">Concerne</th>
                    <th scope="col">Précisions</th>
                  </tr>
                </thead>
                <tbody>
                  {data.results.map((row) => {
                    const href = targetHref(row);
                    return (
                      <tr key={row.id}>
                        <td className="jf-nowrap">{formatDate(row.created_at, true)}</td>
                        <td>{row.actor?.name ?? "—"}</td>
                        <td className="jf-strong">{row.action_label}</td>
                        <td>
                          {href ? (
                            <Link href={href} className="jf-link">
                              {row.target_label}
                            </Link>
                          ) : (
                            row.target_label
                          )}
                        </td>
                        <td>{row.details || "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <Pager count={data.count} base={BASE} params={params} />
        </div>
      </section>
    </>
  );
}
