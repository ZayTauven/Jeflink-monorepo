import type { Metadata } from "next";
import Link from "next/link";

import { consoleGet, type Query } from "@/console/data";
import { ActionButton, Avatar, Flash, Pager, ReasonAction, Tabs } from "@/console/kit";
import { ago, plural } from "@/console/text";
import type { Page, ProRow } from "@/console/types";
import { Empty, PageHead } from "@/console/ui";
import { getTrades } from "@/lib/api";
import { formatRating } from "@/lib/format";

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

      <section className="ax-card" aria-label="Liste des pros">
        <div className="ax-card__body">
          {data.results.length === 0 ? (
            <Empty>{pending ? "Aucun pro en attente de vérification." : "Aucun pro."}</Empty>
          ) : (
            <ul className="ax-list jf-rows">
              {data.results.map((p) => (
                <li key={p.account.id} className="ax-list__row">
                  <span className="ax-list__leading">
                    <Avatar name={p.account.name} photo={p.photo || p.account.photo} size={44} />
                  </span>
                  <span className="ax-list__content">
                    <Link href={`${BASE}/${p.account.id}`} className="ax-list__title jf-link">
                      {p.account.name}
                    </Link>
                    <span className="ax-list__meta">
                      {p.trades.join(", ") || "Aucun métier déclaré"}
                      {p.headline && ` · ${p.headline}`}
                    </span>
                    <span className="ax-list__meta">
                      {pending
                        ? `Inscrit ${ago(p.account.date_joined)} · ${p.account.phone || p.account.email}`
                        : `${plural(p.missions_done, "mission terminée", "missions terminées")} · ${p.rating.count ? `${formatRating(p.rating.average)}/5 (${p.rating.count} avis)` : "pas encore noté"}`}
                    </span>
                    {p.verification_note && (
                      <span className="ax-list__meta jf-flag">Refusé : {p.verification_note}</span>
                    )}
                    {!p.account.is_active && (
                      <span className="ax-list__meta jf-flag">
                        Suspendu : {p.account.suspension_reason}
                      </span>
                    )}
                  </span>
                  {pending && (
                    <span className="ax-list__trailing jf-row-actions">
                      <ActionButton
                        endpoint={`/api/console/pros/${p.account.id}/verify/`}
                        back={back}
                        ok="Pro vérifié : il peut envoyer des devis."
                        label="Vérifier"
                      />
                      <ReasonAction
                        endpoint={`/api/console/pros/${p.account.id}/reject/`}
                        back={back}
                        ok="Refus enregistré : le pro voit le motif dans son espace."
                        label="Refuser…"
                        confirm="Confirmer le refus"
                        placeholder="Ce qui manque, ex. : pièce d'identité illisible."
                      />
                    </span>
                  )}
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
