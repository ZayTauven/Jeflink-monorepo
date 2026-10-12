import type { Metadata } from "next";

import { CardGrid, ReviewCard } from "@/console/cards";
import { consoleGet, type Query } from "@/console/data";
import { Flash, Pager, Tabs } from "@/console/kit";
import type { Page, ReviewRow } from "@/console/types";
import { PageHead } from "@/console/ui";

export const metadata: Metadata = { title: "Avis" };

const BASE = "/console/avis";

export default async function ReviewsPage({ searchParams }: { searchParams: Promise<Query> }) {
  const params = await searchParams;
  const vue = params.vue ?? "";
  const data = await consoleGet<Page<ReviewRow, { all: number; low: number; hidden: number }>>(
    BASE,
    "reviews/",
    {
      low: vue === "basses" ? "1" : undefined,
      hidden: vue === "masques" ? "1" : undefined,
      q: params.q,
      page: params.page,
    },
  );
  const back = `${BASE}${vue ? `?vue=${vue}` : ""}`;

  return (
    <>
      <PageHead
        title="Avis"
        subtitle="Un avis négatif honnête reste visible : c'est la preuve que les notes sont vraies. On ne masque que les avis abusifs (insultes, données personnelles, hors sujet)."
      />
      <Flash ok={params.ok} erreur={params.erreur} />
      <Tabs
        base={BASE}
        params={params}
        name="vue"
        label="Filtre des avis"
        tabs={[
          { value: "", label: "Tous", count: data.facets.all },
          { value: "basses", label: "2/5 ou moins", count: data.facets.low },
          { value: "masques", label: "Masqués", count: data.facets.hidden },
        ]}
      />
      <CardGrid empty="Aucun avis dans cette liste.">
        {data.results.map((r) => (
          <ReviewCard key={r.id} r={r} back={back} />
        ))}
      </CardGrid>
      <Pager count={data.count} base={BASE} params={params} />
    </>
  );
}
