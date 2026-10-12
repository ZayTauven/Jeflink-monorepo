import type { Metadata } from "next";

import { DisputeCard } from "@/console/blocks";
import { consoleGet, type Query } from "@/console/data";
import { Flash, Pager, Tabs } from "@/console/kit";
import type { DisputeRow, Page } from "@/console/types";
import { Empty, PageHead } from "@/console/ui";

export const metadata: Metadata = { title: "Litiges" };

const BASE = "/console/litiges";

export default async function DisputesPage({ searchParams }: { searchParams: Promise<Query> }) {
  const params = await searchParams;
  // Par défaut : les litiges à traiter (ouverts et en cours).
  const etat = params.etat ?? "";
  const data = await consoleGet<Page<DisputeRow>>(BASE, "disputes/", {
    active: etat === "" ? "1" : undefined,
    status: etat && etat !== "tous" ? etat : undefined,
    page: params.page,
  });
  const f = data.facets;
  const back = `${BASE}${etat ? `?etat=${etat}` : ""}`;

  return (
    <>
      <PageHead
        title="Litiges"
        subtitle="Problèmes signalés sur une mission. On appelle les deux parties, puis on écrit une décision : elle apparaît dans leur espace."
      />
      <Flash ok={params.ok} erreur={params.erreur} />
      <Tabs
        base={BASE}
        params={params}
        name="etat"
        label="État des litiges"
        tabs={[
          { value: "", label: "À traiter", count: (f.open ?? 0) + (f.investigating ?? 0) },
          { value: "open", label: "Ouverts", count: f.open ?? 0 },
          { value: "investigating", label: "En cours", count: f.investigating ?? 0 },
          { value: "resolved", label: "Résolus", count: f.resolved ?? 0 },
          { value: "dismissed", label: "Sans suite", count: f.dismissed ?? 0 },
          { value: "tous", label: "Tous" },
        ]}
      />
      {data.results.length === 0 ? (
        <section className="ax-card">
          <div className="ax-card__body">
            <Empty>Aucun litige dans cette liste.</Empty>
          </div>
        </section>
      ) : (
        <div className="jf-stack">
          {data.results.map((d) => (
            <DisputeCard key={d.id} dispute={d} back={back} />
          ))}
        </div>
      )}
      <Pager count={data.count} base={BASE} params={params} />
    </>
  );
}
