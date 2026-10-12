import type { Metadata } from "next";

import { CardGrid } from "@/console/cards";
import { consoleGet, type Query } from "@/console/data";
import { Field } from "@/console/forms";
import { ActionForm, Flash } from "@/console/kit";
import { Submit } from "@/console/submit";
import type { Commissions } from "@/console/types";
import { Card, PageHead } from "@/console/ui";

export const metadata: Metadata = { title: "Commissions" };

const BASE = "/console/commissions";
const NBSP = " ";

export default async function CommissionsPage({ searchParams }: { searchParams: Promise<Query> }) {
  const params = await searchParams;
  const c = await consoleGet<Commissions>(BASE, "commissions/");

  return (
    <>
      <PageHead
        title="Commissions"
        subtitle={`Part de Jeflink sur chaque devis accepté. Le taux est figé à la réservation${NBSP}: le changer ne touche que les prochaines missions.`}
      />
      <Flash ok={params.ok} erreur={params.erreur} />
      <ActionForm endpoint="/api/console/commissions/" back={BASE} ok="Taux enregistrés.">
        <div className="jf-stack">
          <Card title="Taux par défaut" eyebrow="Tous les métiers">
            <div className="jf-form">
              <Field
                id="default"
                label="Commission (%)"
                hint="Appliquée aux métiers qui n'ont pas leur propre taux."
              >
                <input
                  id="default"
                  name="default_commission_percent"
                  type="number"
                  min={0}
                  max={50}
                  required
                  className="ax-input"
                  defaultValue={c.default_commission_percent}
                />
              </Field>
            </div>
          </Card>
          <CardGrid empty="Aucun métier.">
            {c.trades.map((t) => (
              <article key={t.id} className="ax-card jf-item jf-item--compact" aria-label={t.name}>
                <div className="jf-item__head">
                  <span className="jf-kpi-icon" aria-hidden="true">
                    <i className={`bi ${t.icon || "bi-tools"}`} />
                  </span>
                  <div className="jf-item__titles">
                    <span className="ax-card__eyebrow">
                      {t.commission_percent === null ? "Taux par défaut" : "Taux propre"}
                      {!t.is_active && " · masqué"}
                    </span>
                    <h2 className="jf-item__title">{t.name}</h2>
                  </div>
                  <div className="jf-item__aside">
                    <span className="jf-big-rate ax-num">
                      {t.effective}
                      {NBSP}%
                    </span>
                  </div>
                </div>
                <div className="jf-item__foot">
                  <Field
                    id={`trade-${t.id}`}
                    label={
                      <>
                        Taux propre<span className="sr-only">, {t.name}</span> (%)
                      </>
                    }
                    hint="Vide = taux par défaut."
                  >
                    <input
                      id={`trade-${t.id}`}
                      name={`trade_${t.id}`}
                      type="number"
                      min={0}
                      max={50}
                      className="ax-input ax-input--sm"
                      defaultValue={t.commission_percent ?? ""}
                    />
                  </Field>
                </div>
              </article>
            ))}
          </CardGrid>
        </div>
        <div className="jf-sticky-save">
          <Submit>Enregistrer les taux</Submit>
        </div>
      </ActionForm>
    </>
  );
}
