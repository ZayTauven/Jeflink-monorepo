import type { Metadata } from "next";

import { CardGrid, MessageCard } from "@/console/cards";
import { consoleGet, type Query } from "@/console/data";
import { Flash, Pager, Tabs } from "@/console/kit";
import type { ContactRow, Page } from "@/console/types";
import { PageHead } from "@/console/ui";

export const metadata: Metadata = { title: "Messages" };

const BASE = "/console/messages";

export default async function MessagesPage({ searchParams }: { searchParams: Promise<Query> }) {
  const params = await searchParams;
  const vue = params.vue ?? "a-traiter";
  const data = await consoleGet<Page<ContactRow, { todo: number; done: number }>>(
    BASE,
    "messages/",
    {
      handled: vue === "a-traiter" ? "0" : vue === "traites" ? "1" : undefined,
      page: params.page,
    },
  );
  const back = `${BASE}?vue=${vue}`;

  return (
    <>
      <PageHead
        title="Messages"
        subtitle="Messages envoyés depuis la page Contact du site. Répondez par email, puis marquez le message comme traité."
      />
      <Flash ok={params.ok} erreur={params.erreur} />
      <Tabs
        base={BASE}
        params={{ ...params, vue }}
        name="vue"
        label="Filtre des messages"
        tabs={[
          { value: "a-traiter", label: "À traiter", count: data.facets.todo },
          { value: "traites", label: "Traités", count: data.facets.done },
          { value: "tous", label: "Tous" },
        ]}
      />
      <CardGrid empty={vue === "a-traiter" ? "Aucun message en attente." : "Aucun message."}>
        {data.results.map((m) => (
          <MessageCard key={m.id} m={m} back={back} />
        ))}
      </CardGrid>
      <Pager count={data.count} base={BASE} params={params} />
    </>
  );
}
