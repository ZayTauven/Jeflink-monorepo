import type { Metadata } from "next";

import { CardGrid, ProCard } from "@/console/cards";
import { consoleGet, type Query } from "@/console/data";
import { AutoFilters } from "@/console/filters";
import {
  ActiveFilters,
  Flash,
  Pager,
  SortField,
  Tabs,
  withoutFilters,
  type FilterChip,
} from "@/console/kit";
import { plural } from "@/console/text";
import type { Page, ProRow } from "@/console/types";
import { PageHead } from "@/console/ui";
import { getTrades } from "@/lib/api";

export const metadata: Metadata = { title: "Pros" };

const BASE = "/console/pros";

export default async function ProsPage({ searchParams }: { searchParams: Promise<Query> }) {
  const params = await searchParams;
  const etat = params.etat ?? "pending";
  const [data, trades] = await Promise.all([
    consoleGet<
      Page<ProRow, { pending: number; trades: number; verified: number; suspended: number }>
    >(BASE, "pros/", {
      status: etat === "tous" ? undefined : etat,
      trade: params.metier,
      q: params.q,
      sort: params.tri,
      page: params.page,
    }),
    getTrades(),
  ]);
  const f = data.facets;
  const back = `${BASE}?etat=${etat}`;
  const pending = etat === "pending";

  const filters: FilterChip[] = [
    { name: "q", label: "Recherche", value: params.q },
    { name: "metier", label: "Métier", value: trades.find((t) => t.slug === params.metier)?.name },
  ];
  const filtered = filters.some((x) => params[x.name]);

  return (
    <>
      <PageHead
        title="Pros"
        subtitle="Seul un pro vérifié peut envoyer des devis. Vérifiez l'identité et le métier au téléphone avant de valider."
      />
      <Flash ok={params.ok} erreur={params.erreur} />
      <Tabs
        base={BASE}
        params={{ ...params, etat }}
        name="etat"
        label="État des pros"
        tabs={[
          { value: "pending", label: "À vérifier", count: f.pending },
          { value: "trades", label: "Métiers demandés", count: f.trades },
          { value: "verified", label: "Vérifiés", count: f.verified },
          { value: "suspended", label: "Suspendus", count: f.suspended },
          { value: "tous", label: "Tous" },
        ]}
      />
      <AutoFilters
        base={BASE}
        label="Filtrer les pros"
        summary={data.count ? plural(data.count, "pro", "pros") : "Aucun résultat"}
      >
        <input type="hidden" name="etat" value={etat} />
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
        <SortField
          // Hors file d'attente, « name » est le tri par défaut (onglet changé après un tri par nom).
          value={!pending && params.tri === "name" ? "" : params.tri}
          options={[
            ["", pending ? "En attente depuis le plus longtemps" : "Nom, de A à Z"],
            ...(pending ? ([["name", "Nom, de A à Z"]] as [string, string][]) : []),
            ["missions", "Plus de missions réalisées"],
            ["recent", "Inscrits récemment"],
          ]}
        />
        <div className="jf-filters__actions">
          <button type="submit" className="ax-btn ax-btn--primary">
            Filtrer
          </button>
        </div>
      </AutoFilters>
      <ActiveFilters base={BASE} params={params} filters={filters} />

      <CardGrid
        empty={
          filtered
            ? "Aucun pro ne correspond à ces filtres."
            : pending
              ? "Aucun pro en attente de vérification."
              : "Aucun pro."
        }
        clear={
          filtered
            ? withoutFilters(
                BASE,
                params,
                filters.map((x) => x.name),
              )
            : undefined
        }
      >
        {data.results.map((p) => (
          <ProCard key={p.account.id} p={p} back={back} pending={pending} />
        ))}
      </CardGrid>
      <Pager count={data.count} base={BASE} params={params} />
    </>
  );
}
