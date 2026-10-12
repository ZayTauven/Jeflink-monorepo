import type { Metadata } from "next";
import Link from "next/link";

import { CardGrid } from "@/console/cards";
import { consoleGet, qs, type Query } from "@/console/data";
import { Pager, Tabs } from "@/console/kit";
import { ago, plural } from "@/console/text";
import type { Page, Totals, Transaction } from "@/console/types";
import { Kpi, PageHead, Status } from "@/console/ui";
import { getTrades } from "@/lib/api";
import { formatXOF } from "@/lib/format";

export const metadata: Metadata = { title: "Transactions" };

const BASE = "/console/transactions";
const NBSP = " ";

export default async function TransactionsPage({ searchParams }: { searchParams: Promise<Query> }) {
  const params = await searchParams;
  const filters = {
    status: params.statut,
    days: params.jours,
    trade: params.metier,
    coupon: params.code,
    pro: params.pro,
  };
  const [data, trades] = await Promise.all([
    consoleGet<Page<Transaction> & { totals: Totals }>(BASE, "transactions/", {
      ...filters,
      page: params.page,
    }),
    getTrades(),
  ]);
  const t = data.totals;

  return (
    <>
      <PageHead
        title="Transactions"
        subtitle={`Missions réservées et leurs montants. Paiement sur place${NBSP}: le client paie le pro (devis moins remise)${NBSP}; le pro doit la commission à Jeflink, qui lui rembourse la remise.`}
        actions={
          <a
            href={`/console/export/transactions${qs(filters)}`}
            className="ax-btn ax-btn--secondary"
            download
          >
            <i className="bi bi-download" aria-hidden="true" /> Exporter (CSV)
          </a>
        }
      />
      <Tabs
        base={BASE}
        params={params}
        name="statut"
        label="Statut des missions"
        tabs={[
          { value: "", label: "Toutes" },
          { value: "done", label: "Terminées" },
          { value: "booked", label: "En cours" },
        ]}
      />
      <form className="jf-filters" method="get" action={BASE}>
        {params.statut && <input type="hidden" name="statut" value={params.statut} />}
        <div className="ax-field">
          <label className="ax-field__label" htmlFor="jours">
            Réservées depuis
          </label>
          <select id="jours" name="jours" className="ax-select" defaultValue={params.jours ?? ""}>
            <option value="">Toujours</option>
            <option value="7">7 derniers jours</option>
            <option value="30">30 derniers jours</option>
            <option value="90">90 derniers jours</option>
          </select>
        </div>
        {trades.length > 0 && (
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
              {trades.map((tr) => (
                <option key={tr.slug} value={tr.slug}>
                  {tr.name}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="ax-field">
          <label className="ax-field__label" htmlFor="code">
            Code promo
          </label>
          <input
            id="code"
            name="code"
            className="ax-input jf-code"
            defaultValue={params.code}
            placeholder="CLIM20"
            aria-describedby="code-aide"
          />
          <p className="ax-field__hint" id="code-aide">
            «{NBSP}*{NBSP}» pour toutes les missions avec un code.
          </p>
        </div>
        <div className="jf-filters__actions">
          <button type="submit" className="ax-btn ax-btn--primary">
            Filtrer
          </button>
          <Link href={BASE} className="ax-btn ax-btn--ghost">
            Effacer
          </Link>
        </div>
      </form>

      <div className="ax-dash-grid mb-6">
        <Kpi
          label="Volume des devis"
          icon="bi-cash-coin"
          dark
          value={t.volume.toLocaleString("fr-FR")}
          unit="F CFA"
          foot={plural(t.count, "mission", "missions")}
        />
        <Kpi
          label="Part des clients"
          icon="bi-wallet2"
          value={t.client_paid.toLocaleString("fr-FR")}
          unit="F CFA"
          foot="Devis moins remises, payés au pro sur place"
        />
        <Kpi
          label="Remises Jeflink"
          icon="bi-ticket-perforated"
          value={t.discount.toLocaleString("fr-FR")}
          unit="F CFA"
          foot="Financées par Jeflink"
        />
        <Kpi
          label="Net Jeflink"
          icon="bi-graph-up-arrow"
          value={t.net.toLocaleString("fr-FR")}
          unit="F CFA"
          foot={`Commissions ${formatXOF(t.commission)} moins remises`}
        />
      </div>

      <CardGrid empty="Aucune mission ne correspond à ces filtres.">
        {data.results.map((r) => (
          <article key={r.id} className="ax-card jf-item" aria-label={`Mission ${r.id}`}>
            <div className="jf-item__head">
              <div className="jf-item__titles">
                <span className="ax-card__eyebrow">
                  {r.trade} · {r.zone} · {ago(r.updated_at)}
                </span>
                <h2 className="jf-item__title">
                  <Link href={`/console/demandes/${r.id}`} className="jf-link">
                    #{r.id} {r.title}
                  </Link>
                </h2>
              </div>
              <div className="jf-item__aside jf-inline jf-inline--end">
                {r.coupon && <span className="jf-code">{r.coupon}</span>}
                <Status status={r.status} label={r.status_label} />
              </div>
            </div>
            <div className="jf-item__body">
              <dl className="jf-money">
                <div>
                  <dt>Devis</dt>
                  <dd>{formatXOF(r.price)}</dd>
                </div>
                <div>
                  <dt>Remise</dt>
                  <dd>{r.discount ? `−${formatXOF(r.discount)}` : "—"}</dd>
                </div>
                <div>
                  <dt>Part du client</dt>
                  <dd>{formatXOF(r.client_pays)}</dd>
                </div>
                <div>
                  <dt>
                    Commission ({r.commission_rate}
                    {NBSP}%)
                  </dt>
                  <dd>{formatXOF(r.commission)}</dd>
                </div>
                <div className="jf-money__total">
                  <dt>Net Jeflink</dt>
                  <dd className={r.net < 0 ? "jf-flag" : ""}>{formatXOF(r.net)}</dd>
                </div>
              </dl>
            </div>
            <div className="jf-item__foot">
              <dl className="jf-item__stats">
                <div>
                  <dt>Client</dt>
                  <dd>
                    <Link href={`/console/clients/${r.client.id}`} className="jf-link">
                      {r.client.name}
                    </Link>
                  </dd>
                </div>
                <div>
                  <dt>Pro</dt>
                  <dd>
                    {r.pro ? (
                      <Link href={`/console/soldes/${r.pro.id}`} className="jf-link">
                        {r.pro.name}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </dd>
                </div>
              </dl>
            </div>
          </article>
        ))}
      </CardGrid>
      <Pager count={data.count} base={BASE} params={params} />
    </>
  );
}
