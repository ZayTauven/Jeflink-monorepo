import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { COUPON_STATE, couponValue } from "@/console/coupons";
import { consoleGet, type Query } from "@/console/data";
import { CouponForm } from "@/console/forms";
import { Facts, Flash } from "@/console/kit";
import type { CouponAdmin, TradeAdmin, ZoneAdmin } from "@/console/types";
import { Card, Meter, PageHead } from "@/console/ui";
import { formatXOF } from "@/lib/format";

type Props = { params: Promise<{ id: string }>; searchParams: Promise<Query> };

export const metadata: Metadata = { title: "Code promo" };

export default async function CouponPage({ params, searchParams }: Props) {
  const [{ id }, flash] = await Promise.all([params, searchParams]);
  if (!/^\d+$/.test(id)) notFound();
  const here = `/console/promos/${id}`;
  const [c, trades, zones] = await Promise.all([
    consoleGet<CouponAdmin>(here, `coupons/${id}/`),
    consoleGet<TradeAdmin[]>(here, "trades/"),
    consoleGet<ZoneAdmin[]>(here, "zones/"),
  ]);
  const state = COUPON_STATE[c.state];

  return (
    <>
      <p className="jf-back">
        <Link href="/console/promos" className="jf-link">
          ← Tous les codes
        </Link>
      </p>
      <PageHead
        title={c.code}
        subtitle={
          <span className="jf-inline">
            <span className={`jf-status ${state.cls}`}>{state.label}</span>
            <span>{couponValue(c)}</span>
          </span>
        }
      />
      <Flash ok={flash.ok} erreur={flash.erreur} />
      <div className="ax-dash-grid">
        <section className="ax-card ax-col--8" aria-label="Modifier le code promo">
          <div className="ax-card__body">
            <CouponForm coupon={c} trades={trades} zones={zones} back={here} prefix="code" />
          </div>
        </section>
        <div className="ax-col--4 jf-col-md-full jf-stack">
          <Card title="Utilisation" eyebrow="Résultats">
            <Facts
              items={[
                [
                  "Réservations",
                  <>
                    {c.uses}
                    {c.max_uses ? ` sur ${c.max_uses} prévues` : ""}
                    {c.max_uses ? <Meter value={c.uses} max={c.max_uses} /> : null}
                  </>,
                ],
                ["Remises accordées", formatXOF(c.discount_total)],
              ]}
            />
            <Link href={`/console/transactions?code=${c.code}`} className="jf-link">
              Voir les missions avec ce code →
            </Link>
          </Card>
        </div>
      </div>
    </>
  );
}
