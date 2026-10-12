import type { Metadata } from "next";

import { consoleGet, type Query } from "@/console/data";
import { ActionButton, Flash, Pager, Tabs } from "@/console/kit";
import { ago } from "@/console/text";
import type { ContactRow, Page } from "@/console/types";
import { Empty, PageHead } from "@/console/ui";

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
      <section className="ax-card" aria-label="Liste des messages">
        <div className="ax-card__body">
          {data.results.length === 0 ? (
            <Empty>{vue === "a-traiter" ? "Aucun message en attente." : "Aucun message."}</Empty>
          ) : (
            <ul className="ax-list jf-rows">
              {data.results.map((m) => (
                <li key={m.id} className="ax-list__row">
                  <span className="ax-list__content">
                    <span className="ax-list__title jf-inline">
                      {m.name}
                      {m.is_handled && <span className="jf-status jf-status--done">Traité</span>}
                    </span>
                    <span className="jf-prose">{m.message}</span>
                    <span className="ax-list__meta">
                      <a
                        className="jf-link"
                        href={`mailto:${m.email}?subject=${encodeURIComponent("Votre message à Jeflink")}`}
                      >
                        {m.email}
                      </a>{" "}
                      · reçu {ago(m.created_at)}
                      {m.is_handled &&
                        m.handled_by &&
                        ` · traité par ${m.handled_by.name}${m.handled_at ? ` ${ago(m.handled_at)}` : ""}`}
                    </span>
                  </span>
                  <span className="ax-list__trailing">
                    {m.is_handled ? (
                      <ActionButton
                        endpoint={`/api/console/messages/${m.id}/reopen/`}
                        back={back}
                        ok="Message remis à traiter."
                        label="Rouvrir"
                        variant="ax-btn ax-btn--ghost ax-btn--sm"
                      />
                    ) : (
                      <ActionButton
                        endpoint={`/api/console/messages/${m.id}/handle/`}
                        back={back}
                        ok="Message marqué comme traité."
                        label="Marquer traité"
                      />
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <Pager count={data.count} base={BASE} params={params} />
        </div>
      </section>
    </>
  );
}
