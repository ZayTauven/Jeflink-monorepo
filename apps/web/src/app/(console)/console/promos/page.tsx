import type { Metadata } from "next";
import Link from "next/link";

import { CardGrid } from "@/console/cards";
import { COUPON_STATE, couponRules, couponValue } from "@/console/coupons";
import { consoleGet, type Query } from "@/console/data";
import { CouponForm } from "@/console/forms";
import { Flash } from "@/console/kit";
import { plural } from "@/console/text";
import type { CouponAdmin, TradeAdmin, ZoneAdmin } from "@/console/types";
import { PageHead } from "@/console/ui";
import { formatDate, formatXOF } from "@/lib/format";

export const metadata: Metadata = { title: "Codes promo" };

const BASE = "/console/promos";
const NBSP = " ";

export default async function CouponsPage({ searchParams }: { searchParams: Promise<Query> }) {
  const params = await searchParams;
  const [coupons, trades, zones] = await Promise.all([
    consoleGet<CouponAdmin[]>(BASE, "coupons/"),
    consoleGet<TradeAdmin[]>(BASE, "trades/"),
    consoleGet<ZoneAdmin[]>(BASE, "zones/"),
  ]);
  const live = coupons.filter((c) => c.state === "active").length;
  const given = coupons.reduce((n, c) => n + c.discount_total, 0);

  return (
    <>
      <PageHead
        title="Codes promo"
        subtitle={`${plural(live, "code en cours", "codes en cours")}, ${formatXOF(given)} de remises accordées. Les remises sont financées par Jeflink${NBSP}: le pro touche toujours son devis complet.`}
        actions={
          <details className="jf-reason jf-new" suppressHydrationWarning>
            <summary className="ax-btn ax-btn--primary">Nouveau code</summary>
            <div className="ax-card jf-new__panel">
              <div className="ax-card__body">
                <CouponForm trades={trades} zones={zones} back={BASE} prefix="nouveau" />
              </div>
            </div>
          </details>
        }
      />
      <Flash ok={params.ok} erreur={params.erreur} />
      <CardGrid empty="Aucun code promo pour l'instant.">
        {coupons.map((c) => {
          const state = COUPON_STATE[c.state];
          return (
            <article key={c.id} className="ax-card jf-item" aria-label={`Code ${c.code}`}>
              <div className="jf-item__head">
                <div className="jf-item__titles">
                  <span className="ax-card__eyebrow">{couponValue(c)}</span>
                  <h2 className="jf-item__title">
                    <Link href={`${BASE}/${c.id}`} className="jf-link jf-code">
                      {c.code}
                    </Link>
                  </h2>
                </div>
                <div className="jf-item__aside">
                  <span className={`jf-status ${state.cls}`}>{state.label}</span>
                </div>
              </div>
              <div className="jf-item__body">
                {c.description && <p className="jf-prose">{c.description}</p>}
                <ul className="jf-chips" aria-label="Conditions">
                  {couponRules(c).map((rule) => (
                    <li key={rule}>{rule}</li>
                  ))}
                </ul>
              </div>
              <div className="jf-item__foot">
                <dl className="jf-item__stats">
                  <div>
                    <dt>Utilisations</dt>
                    <dd className="ax-num">
                      {c.uses}
                      {c.max_uses ? ` / ${c.max_uses}` : ""}
                    </dd>
                  </div>
                  <div>
                    <dt>Remises accordées</dt>
                    <dd className="ax-num">{formatXOF(c.discount_total)}</dd>
                  </div>
                  <div>
                    <dt>Période</dt>
                    <dd>
                      {c.starts_on
                        ? `${c.ends_on ? "" : "Depuis le "}${formatDate(c.starts_on)}`
                        : "Dès maintenant"}
                      {c.ends_on ? ` → ${formatDate(c.ends_on)}` : ""}
                    </dd>
                  </div>
                </dl>
                <div className="jf-item__actions">
                  <Link href={`${BASE}/${c.id}`} className="ax-btn ax-btn--secondary ax-btn--sm">
                    Modifier
                  </Link>
                </div>
              </div>
            </article>
          );
        })}
      </CardGrid>
    </>
  );
}
