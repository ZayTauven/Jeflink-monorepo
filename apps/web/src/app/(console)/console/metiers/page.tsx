import type { Metadata } from "next";
import Link from "next/link";

import { CardGrid } from "@/console/cards";
import { consoleGet, type Query } from "@/console/data";
import { TradeForm } from "@/console/forms";
import { Flash } from "@/console/kit";
import { Modal } from "@/console/modal";
import { plural } from "@/console/text";
import type { TradeAdmin } from "@/console/types";
import { PageHead } from "@/console/ui";
import { formatXOF } from "@/lib/format";

export const metadata: Metadata = { title: "Métiers" };

const BASE = "/console/metiers";

export default async function TradesPage({ searchParams }: { searchParams: Promise<Query> }) {
  const params = await searchParams;
  const trades = await consoleGet<TradeAdmin[]>(BASE, "trades/");
  const active = trades.filter((t) => t.is_active).length;

  return (
    <>
      <PageHead
        title="Métiers"
        subtitle={`${plural(active, "métier proposé", "métiers proposés")} sur le site. Un métier se masque, il ne se supprime pas : les demandes passées gardent leur métier.`}
        actions={
          <Modal trigger="Nouveau métier" triggerClassName="ax-btn ax-btn--primary" title="Nouveau métier" subtitle="Il apparaît sur le site dès qu'il est proposé." size="lg">
            <TradeForm back={BASE} prefix="nouveau" />
          </Modal>
        }
      />
      <Flash ok={params.ok} erreur={params.erreur} />
      <CardGrid empty="Aucun métier pour l'instant.">
        {trades.map((t) => (
          <article key={t.id} className="ax-card jf-item" aria-label={t.name}>
            <div className="jf-item__head">
              <span className="jf-kpi-icon" aria-hidden="true">
                <i className={`bi ${t.icon || "bi-tools"}`} />
              </span>
              <div className="jf-item__titles">
                <span className="ax-card__eyebrow">Ordre {t.position}</span>
                <h2 className="jf-item__title">
                  <Link href={`${BASE}/${t.id}`} className="jf-link">
                    {t.name}
                  </Link>
                </h2>
              </div>
              <div className="jf-item__aside">
                <span
                  className={`jf-status ${t.is_active ? "jf-status--done" : "jf-status--cancelled"}`}
                >
                  {t.is_active ? "Sur le site" : "Masqué"}
                </span>
              </div>
            </div>
            <div className="jf-item__body">
              {t.tagline && <p className="jf-prose">{t.tagline}</p>}
              {t.services.length > 0 && (
                <ul className="jf-chips" aria-label="Prestations courantes">
                  {t.services.slice(0, 6).map((service) => (
                    <li key={service}>{service}</li>
                  ))}
                  {t.services.length > 6 && <li>+{t.services.length - 6}</li>}
                </ul>
              )}
            </div>
            <div className="jf-item__foot">
              <dl className="jf-item__stats">
                <div>
                  <dt>Pros vérifiés</dt>
                  <dd className="ax-num">{t.pros_verified}</dd>
                </div>
                <div>
                  <dt>Demandes (30 j)</dt>
                  <dd className="ax-num">{t.requests_30d}</dd>
                </div>
                <div>
                  <dt>À partir de</dt>
                  <dd className="ax-num">
                    {t.starting_price === null ? "—" : formatXOF(t.starting_price)}
                  </dd>
                </div>
              </dl>
              <div className="jf-item__actions">
                <Link href={`${BASE}/${t.id}`} className="ax-btn ax-btn--secondary ax-btn--sm">
                  Modifier
                </Link>
              </div>
            </div>
          </article>
        ))}
      </CardGrid>
    </>
  );
}
