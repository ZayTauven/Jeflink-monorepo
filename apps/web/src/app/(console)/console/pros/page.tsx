import type { Metadata } from "next";

import { CardGrid, ProCard } from "@/console/cards";
import { consoleGet, type Query } from "@/console/data";
import { Flash, Pager, Tabs } from "@/console/kit";
import type { Page, ProRow } from "@/console/types";
import { PageHead } from "@/console/ui";
import { getTrades } from "@/lib/api";

export const metadata: Metadata = { title: "Pros" };

const BASE = "/console/pros";

export default async function ProsPage({ searchParams }: { searchParams: Promise<Query> }) {
  const params = await searchParams;
  const etat = params.etat ?? "pending";
  const [data, trades] = await Promise.all([
    consoleGet<Page<ProRow, { pending: number; verified: number; suspended: number }>>(
      BASE,
      "pros/",
      {
        status: etat === "tous" ? undefined : etat,
        trade: params.metier,
        q: params.q,
        page: params.page,
      },
    ),
    getTrades(),
  ]);
  const f = data.facets;
  const back = `${BASE}?etat=${etat}`;
  const pending = etat === "pending";

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
          { value: "verified", label: "Vérifiés", count: f.verified },
          { value: "suspended", label: "Suspendus", count: f.suspended },
          { value: "tous", label: "Tous" },
        ]}
      />
      <form className="jf-filters" method="get" action={BASE} role="search">
        <input type="hidden" name="etat" value={etat} />
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
        <div className="jf-filters__actions">
          <button type="submit" className="ax-btn ax-btn--primary">
            Filtrer
          </button>
        </div>
      </form>

      <CardGrid empty={pending ? "Aucun pro en attente de vérification." : "Aucun pro."}>
        {data.results.map((p) => (
          <ProCard key={p.account.id} p={p} back={back} pending={pending} />
        ))}
      </CardGrid>
      <Pager count={data.count} base={BASE} params={params} />
    </>
  );
}
