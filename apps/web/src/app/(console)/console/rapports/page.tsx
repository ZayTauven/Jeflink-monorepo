import type { Metadata } from "next";
import Link from "next/link";

import { CardGrid } from "@/console/cards";
import { consoleGet, type Query } from "@/console/data";
import { plural } from "@/console/text";
import type { Reports } from "@/console/types";
import { Kpi, PageHead } from "@/console/ui";
import { formatXOF } from "@/lib/format";

export const metadata: Metadata = { title: "Rapports" };

const BASE = "/console/rapports";

const monthName = new Intl.DateTimeFormat("fr-FR", {
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});

function label(month: string): string {
  const text = monthName.format(new Date(`${month}-01T00:00:00Z`));
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export default async function ReportsPage({ searchParams }: { searchParams: Promise<Query> }) {
  const params = await searchParams;
  const data = await consoleGet<Reports>(BASE, "reports/", {
    month: /^\d{4}-\d{2}$/.test(params.mois ?? "") ? params.mois : undefined,
  });
  const current = data.months.find((m) => m.month === data.month) ?? data.months[0];

  return (
    <>
      <PageHead
        title="Rapports"
        subtitle="Missions terminées par mois : ce que les clients ont payé, ce que Jeflink a gagné, ce que les codes promo ont coûté."
        actions={
          <a href="/console/export/rapports" className="ax-btn ax-btn--secondary" download>
            <i className="bi bi-download" aria-hidden="true" /> Exporter 12 mois (CSV)
          </a>
        }
      />

      <h2 className="jf-section-title">{label(current.month)}</h2>
      <div className="ax-dash-grid mb-6">
        <Kpi
          label="Missions terminées"
          icon="bi-patch-check"
          dark
          value={String(current.count)}
          foot={`${plural(current.requests, "demande publiée", "demandes publiées")}, ${plural(current.booked, "réservée", "réservées")}`}
        />
        <Kpi
          label="Volume des devis"
          icon="bi-cash-coin"
          value={current.volume.toLocaleString("fr-FR")}
          unit="F CFA"
        />
        <Kpi
          label="Remises Jeflink"
          icon="bi-ticket-perforated"
          value={current.discount.toLocaleString("fr-FR")}
          unit="F CFA"
          foot={plural(current.coupons_used, "code promo utilisé", "codes promo utilisés")}
        />
        <Kpi
          label="Net Jeflink"
          icon="bi-graph-up-arrow"
          value={current.net.toLocaleString("fr-FR")}
          unit="F CFA"
          foot={`Commissions ${formatXOF(current.commission)}`}
        />
      </div>

      <h2 className="jf-section-title">Par métier</h2>
      <CardGrid empty="Aucune mission terminée ce mois-ci.">
        {data.by_trade.map((t) => (
          <article key={t.trade} className="ax-card jf-item jf-item--compact" aria-label={t.trade}>
            <div className="jf-item__head">
              <span className="jf-kpi-icon" aria-hidden="true">
                <i className={`bi ${t.icon || "bi-tools"}`} />
              </span>
              <div className="jf-item__titles">
                <span className="ax-card__eyebrow">{plural(t.count, "mission", "missions")}</span>
                <h3 className="jf-item__title">{t.trade}</h3>
              </div>
            </div>
            <dl className="jf-money">
              <div>
                <dt>Volume</dt>
                <dd>{formatXOF(t.volume)}</dd>
              </div>
              <div>
                <dt>Remises</dt>
                <dd>{t.discount ? `−${formatXOF(t.discount)}` : "—"}</dd>
              </div>
              <div className="jf-money__total">
                <dt>Net Jeflink</dt>
                <dd>{formatXOF(t.net)}</dd>
              </div>
            </dl>
          </article>
        ))}
      </CardGrid>

      <h2 className="jf-section-title">Six derniers mois</h2>
      <CardGrid empty="Pas encore d'historique.">
        {data.months.map((m) => (
          <article
            key={m.month}
            className={`ax-card jf-item jf-item--compact${m.month === data.month ? " jf-item--current" : ""}`}
            aria-label={label(m.month)}
          >
            <div className="jf-item__head">
              <div className="jf-item__titles">
                <span className="ax-card__eyebrow">
                  {plural(m.count, "mission terminée", "missions terminées")}
                </span>
                <h3 className="jf-item__title">
                  <Link href={`${BASE}?mois=${m.month}`} className="jf-link">
                    {label(m.month)}
                  </Link>
                </h3>
              </div>
            </div>
            <dl className="jf-money">
              <div>
                <dt>Volume</dt>
                <dd>{formatXOF(m.volume)}</dd>
              </div>
              <div>
                <dt>Remises</dt>
                <dd>{m.discount ? `−${formatXOF(m.discount)}` : "—"}</dd>
              </div>
              <div className="jf-money__total">
                <dt>Net Jeflink</dt>
                <dd>{formatXOF(m.net)}</dd>
              </div>
            </dl>
          </article>
        ))}
      </CardGrid>
    </>
  );
}
