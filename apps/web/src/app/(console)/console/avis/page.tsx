import type { Metadata } from "next";
import Link from "next/link";

import { consoleGet, type Query } from "@/console/data";
import { ActionButton, Flash, Pager, ReasonAction, Stars, Tabs } from "@/console/kit";
import { ago } from "@/console/text";
import type { Page, ReviewRow } from "@/console/types";
import { Empty, PageHead } from "@/console/ui";

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
      <section className="ax-card" aria-label="Liste des avis">
        <div className="ax-card__body">
          {data.results.length === 0 ? (
            <Empty>Aucun avis dans cette liste.</Empty>
          ) : (
            <ul className="ax-list jf-rows">
              {data.results.map((r) => (
                <li key={r.id} className="ax-list__row">
                  <span className="ax-list__content">
                    <span className="ax-list__title jf-inline">
                      <Stars rating={r.rating} />
                      {r.is_hidden && (
                        <span className="jf-status jf-status--cancelled">Masqué</span>
                      )}
                    </span>
                    <span className="jf-prose">
                      {r.comment ? `« ${r.comment} »` : "Sans commentaire."}
                    </span>
                    <span className="ax-list__meta">
                      <Link href={`/console/clients/${r.client.id}`} className="jf-link">
                        {r.client.name}
                      </Link>{" "}
                      <span aria-hidden="true">→</span>
                      <span className="ax-visually-hidden">à propos de</span>{" "}
                      {r.pro ? (
                        <Link href={`/console/pros/${r.pro.id}`} className="jf-link">
                          {r.pro.name}
                        </Link>
                      ) : (
                        "un pro"
                      )}{" "}
                      · {r.request.trade} ·{" "}
                      <Link href={`/console/demandes/${r.request.id}`} className="jf-link">
                        #{r.request.id}
                      </Link>{" "}
                      · {ago(r.created_at)}
                    </span>
                    {r.is_hidden && (
                      <span className="ax-list__meta jf-flag">Motif : {r.hidden_reason}</span>
                    )}
                  </span>
                  <span className="ax-list__trailing jf-row-actions">
                    {r.is_hidden ? (
                      <ActionButton
                        endpoint={`/api/console/reviews/${r.id}/show/`}
                        back={back}
                        ok="Avis rétabli : il compte de nouveau dans la note du pro."
                        label="Rétablir"
                        variant="ax-btn ax-btn--secondary ax-btn--sm"
                      />
                    ) : (
                      <ReasonAction
                        endpoint={`/api/console/reviews/${r.id}/hide/`}
                        back={back}
                        ok="Avis masqué : il sort du site et de la note du pro."
                        label="Masquer…"
                        confirm="Masquer l'avis"
                        placeholder="Ex. : insultes, numéro de téléphone dans le texte."
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
