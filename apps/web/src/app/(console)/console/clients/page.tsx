import type { Metadata } from "next";

import { CardGrid, ClientCard } from "@/console/cards";
import { consoleGet, type Query } from "@/console/data";
import { AutoFilters } from "@/console/filters";
import { ActiveFilters, Flash, Pager, Tabs, withoutFilters, type FilterChip } from "@/console/kit";
import { plural } from "@/console/text";
import type { ClientRow, Page } from "@/console/types";
import { PageHead } from "@/console/ui";

export const metadata: Metadata = { title: "Clients" };

const BASE = "/console/clients";

export default async function ClientsPage({ searchParams }: { searchParams: Promise<Query> }) {
  const params = await searchParams;
  const data = await consoleGet<Page<ClientRow, { active: number; suspended: number }>>(
    BASE,
    "clients/",
    { status: params.etat, q: params.q, page: params.page },
  );

  const filters: FilterChip[] = [{ name: "q", label: "Recherche", value: params.q }];

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
      <AutoFilters
        base={BASE}
        label="Rechercher un client"
        summary={data.count ? plural(data.count, "client", "clients") : "Aucun résultat"}
      >
        {params.etat && <input type="hidden" name="etat" value={params.etat} />}
        <div className="ax-field">
          <label className="ax-field__label" htmlFor="q">
            Rechercher
          </label>
          <input
            id="q"
            name="q"
            type="search"
            autoComplete="off"
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
      </AutoFilters>
      <ActiveFilters base={BASE} params={params} filters={filters} />

      <CardGrid
        empty={params.q ? "Aucun client ne correspond à cette recherche." : "Aucun client."}
        clear={params.q ? withoutFilters(BASE, params, ["q"]) : undefined}
      >
        {data.results.map((c) => (
          <ClientCard key={c.id} c={c} />
        ))}
      </CardGrid>
      <Pager count={data.count} base={BASE} params={params} />
    </>
  );
}
