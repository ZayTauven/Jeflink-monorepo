import type { Metadata } from "next";
import Link from "next/link";

import { consoleGet, type Query } from "@/console/data";
import { Flash, Pager, Tabs } from "@/console/kit";
import { ago } from "@/console/text";
import type { ClientRow, Page } from "@/console/types";
import { Empty, PageHead } from "@/console/ui";
import { formatXOF } from "@/lib/format";

export const metadata: Metadata = { title: "Clients" };

const BASE = "/console/clients";

export default async function ClientsPage({ searchParams }: { searchParams: Promise<Query> }) {
  const params = await searchParams;
  const data = await consoleGet<Page<ClientRow, { active: number; suspended: number }>>(
    BASE,
    "clients/",
    { status: params.etat, q: params.q, page: params.page },
  );

  return (
    <>
      <PageHead
        title="Clients"
        subtitle="Particuliers et entreprises qui publient des demandes. Les plus récents d'abord."
      />
      <Flash ok={params.ok} erreur={params.erreur} />
      <Tabs
        base={BASE}
        params={params}
        name="etat"
        label="État des comptes"
        tabs={[
          { value: "", label: "Tous", count: data.facets.active + data.facets.suspended },
          { value: "active", label: "Actifs", count: data.facets.active },
          { value: "suspended", label: "Suspendus", count: data.facets.suspended },
        ]}
      />
      <form className="jf-filters" method="get" action={BASE} role="search">
        {params.etat && <input type="hidden" name="etat" value={params.etat} />}
        <div className="ax-field">
          <label className="ax-field__label" htmlFor="q">
            Rechercher
          </label>
          <input
            id="q"
            name="q"
            className="ax-input"
            defaultValue={params.q}
            placeholder="Nom, email, téléphone"
          />
        </div>
        <div className="jf-filters__actions">
          <button type="submit" className="ax-btn ax-btn--primary">
            Rechercher
          </button>
        </div>
      </form>

      <section className="ax-card" aria-label="Liste des clients">
        <div className="ax-card__body">
          {data.results.length === 0 ? (
            <Empty>Aucun client trouvé.</Empty>
          ) : (
            <div
              className="ax-table-wrap"
              role="region"
              aria-label="Tableau des clients (défile horizontalement)"
              tabIndex={0}
            >
              <table className="ax-table ax-table--hover">
                <thead>
                  <tr>
                    <th scope="col">Client</th>
                    <th scope="col">Téléphone</th>
                    <th scope="col">Demandes</th>
                    <th scope="col" style={{ textAlign: "end" }}>
                      Missions terminées
                    </th>
                    <th scope="col">Dernière demande</th>
                    <th scope="col">Inscrit</th>
                  </tr>
                </thead>
                <tbody>
                  {data.results.map((c) => (
                    <tr key={c.id}>
                      <td>
                        <Link href={`${BASE}/${c.id}`} className="jf-link jf-strong">
                          {c.name}
                        </Link>
                        <span className="jf-sub">
                          {c.email}
                          {!c.is_active && <span className="jf-flag"> · Suspendu</span>}
                        </span>
                      </td>
                      <td className="jf-nowrap">{c.phone || "—"}</td>
                      <td className="ax-num">{c.requests_count}</td>
                      <td className="ax-num jf-nowrap" style={{ textAlign: "end" }}>
                        {formatXOF(c.spent)}
                      </td>
                      <td className="jf-nowrap">
                        {c.last_request_at ? ago(c.last_request_at) : "—"}
                      </td>
                      <td className="jf-nowrap">{ago(c.date_joined)}</td>
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
