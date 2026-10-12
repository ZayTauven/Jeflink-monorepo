import type { Metadata } from "next";
import Link from "next/link";

import { consoleGet, type Query } from "@/console/data";
import { Flash, Pager, Tabs } from "@/console/kit";
import { ago } from "@/console/text";
import type { Page, RequestRow } from "@/console/types";
import { Empty, PageHead, Status } from "@/console/ui";
import { getTrades, getZones } from "@/lib/api";
import { formatXOF } from "@/lib/format";

export const metadata: Metadata = { title: "Demandes" };

const BASE = "/console/demandes";

export default async function RequestsPage({ searchParams }: { searchParams: Promise<Query> }) {
  const params = await searchParams;
  const [data, trades, zones] = await Promise.all([
    consoleGet<Page<RequestRow>>(BASE, "requests/", {
      status: params.statut,
      trade: params.metier,
      zone: params.quartier,
      q: params.q,
      urgent: params.urgent,
      stale: params.sans_devis,
      dispute: params.litige,
      page: params.page,
    }),
    getTrades(),
    getZones(),
  ]);
  const f = data.facets;
  const total = Object.values(f).reduce((a, b) => a + b, 0);

  return (
    <>
      <PageHead
        title="Demandes"
        subtitle="Toutes les demandes des clients, à chaque étape. Ouvrez une demande pour voir ses devis, son historique et agir."
      />
      <Flash ok={params.ok} erreur={params.erreur} />
      <Tabs
        base={BASE}
        params={params}
        name="statut"
        label="Statut"
        tabs={[
          { value: "", label: "Toutes", count: total },
          { value: "open", label: "En attente de devis", count: f.open ?? 0 },
          { value: "booked", label: "Pro réservé", count: f.booked ?? 0 },
          { value: "done", label: "Terminées", count: f.done ?? 0 },
          { value: "cancelled", label: "Annulées", count: f.cancelled ?? 0 },
        ]}
      />

      <form className="jf-filters" method="get" action={BASE} role="search">
        {params.statut && <input type="hidden" name="statut" value={params.statut} />}
        <div className="ax-field">
          <label className="ax-field__label" htmlFor="q">
            Rechercher
          </label>
          <input
            id="q"
            name="q"
            className="ax-input"
            defaultValue={params.q}
            placeholder="N°, titre, client ou pro"
          />
        </div>
        <div className="ax-field">
          <label className="ax-field__label" htmlFor="metier">
            Métier
          </label>
          <select
            id="metier"
            name="metier"
            className="ax-select"
            defaultValue={params.metier ?? ""}
          >
            <option value="">Tous</option>
            {trades.map((t) => (
              <option key={t.slug} value={t.slug}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
        <div className="ax-field">
          <label className="ax-field__label" htmlFor="quartier">
            Quartier
          </label>
          <select
            id="quartier"
            name="quartier"
            className="ax-select"
            defaultValue={params.quartier ?? ""}
          >
            <option value="">Tous</option>
            {zones.map((z) => (
              <option key={z.slug} value={z.slug}>
                {z.name}
              </option>
            ))}
          </select>
        </div>
        <fieldset className="jf-checks">
          <legend className="ax-field__label">Afficher seulement</legend>
          <label>
            <input type="checkbox" name="urgent" value="1" defaultChecked={params.urgent === "1"} />{" "}
            Urgentes
          </label>
          <label>
            <input
              type="checkbox"
              name="sans_devis"
              value="1"
              defaultChecked={params.sans_devis === "1"}
            />{" "}
            Sans devis depuis 24&nbsp;h
          </label>
          <label>
            <input type="checkbox" name="litige" value="1" defaultChecked={params.litige === "1"} />{" "}
            Avec un litige en cours
          </label>
        </fieldset>
        <div className="jf-filters__actions">
          <button type="submit" className="ax-btn ax-btn--primary">
            Filtrer
          </button>
          <Link href={BASE} className="ax-btn ax-btn--ghost">
            Effacer
          </Link>
        </div>
      </form>

      <section className="ax-card" aria-label="Liste des demandes">
        <div className="ax-card__body">
          {data.results.length === 0 ? (
            <Empty>Aucune demande ne correspond à ces filtres.</Empty>
          ) : (
            <div
              className="ax-table-wrap"
              role="region"
              aria-label="Tableau des demandes (défile horizontalement)"
              tabIndex={0}
            >
              <table className="ax-table ax-table--hover">
                <thead>
                  <tr>
                    <th scope="col">Demande</th>
                    <th scope="col">Client</th>
                    <th scope="col">Pro</th>
                    <th scope="col">Devis</th>
                    <th scope="col" style={{ textAlign: "end" }}>
                      Montant
                    </th>
                    <th scope="col">Statut</th>
                    <th scope="col">Publiée</th>
                  </tr>
                </thead>
                <tbody>
                  {data.results.map((r) => (
                    <tr key={r.id}>
                      <td>
                        <Link href={`${BASE}/${r.id}`} className="jf-link jf-strong">
                          #{r.id} {r.title}
                        </Link>
                        <span className="jf-sub">
                          <i className={`bi ${r.trade.icon}`} aria-hidden="true" /> {r.trade.name} ·{" "}
                          {r.zone.name}
                          {r.is_urgent && <span className="jf-flag"> · Urgent</span>}
                          {r.open_disputes > 0 && <span className="jf-flag"> · Litige</span>}
                        </span>
                      </td>
                      <td>
                        <Link href={`/console/clients/${r.client.id}`} className="jf-link">
                          {r.client.name}
                        </Link>
                      </td>
                      <td>
                        {r.pro ? (
                          <Link href={`/console/pros/${r.pro.id}`} className="jf-link">
                            {r.pro.name}
                          </Link>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="ax-num">{r.quotes_count}/3</td>
                      <td className="ax-num jf-nowrap" style={{ textAlign: "end" }}>
                        {r.amount === null ? "—" : formatXOF(r.amount)}
                      </td>
                      <td>
                        <Status status={r.status} label={r.status_label} />
                      </td>
                      <td className="jf-nowrap">{ago(r.created_at)}</td>
                    </tr>
                  ))}
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
