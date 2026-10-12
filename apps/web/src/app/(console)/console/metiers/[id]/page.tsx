import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { consoleGet, type Query } from "@/console/data";
import { TradeForm } from "@/console/forms";
import { Facts, Flash } from "@/console/kit";
import type { TradeAdmin } from "@/console/types";
import { Card, PageHead } from "@/console/ui";

type Props = { params: Promise<{ id: string }>; searchParams: Promise<Query> };

export const metadata: Metadata = { title: "Modifier un métier" };

export default async function TradePage({ params, searchParams }: Props) {
  const [{ id }, flash] = await Promise.all([params, searchParams]);
  if (!/^\d+$/.test(id)) notFound();
  const here = `/console/metiers/${id}`;
  const t = await consoleGet<TradeAdmin>(here, `trades/${id}/`);

  return (
    <>
      <p className="jf-back">
        <Link href="/console/metiers" className="jf-link">
          ← Tous les métiers
        </Link>
      </p>
      <PageHead
        title={t.name}
        subtitle={
          t.is_active ? (
            <>
              Visible sur le site{" "}
              <a href={`/metiers/${t.slug}`} className="jf-link">
                /metiers/{t.slug}
              </a>
            </>
          ) : (
            "Masqué : absent du site et des nouvelles demandes."
          )
        }
      />
      <Flash ok={flash.ok} erreur={flash.erreur} />
      <div className="ax-dash-grid">
        <section className="ax-card ax-col--8" aria-label="Modifier le métier">
          <div className="ax-card__body">
            <TradeForm trade={t} back={here} prefix="metier" />
          </div>
        </section>
        <div className="ax-col--4 jf-col-md-full jf-stack">
          <Card title="En chiffres" eyebrow="Activité">
            <Facts
              items={[
                ["Pros vérifiés", String(t.pros_verified)],
                ["Demandes sur 30 jours", String(t.requests_30d)],
                ["Demandes au total", String(t.requests_total)],
                ["Adresse", `/metiers/${t.slug}`],
              ]}
            />
            <Link href={`/console/demandes?metier=${t.slug}`} className="jf-link">
              Voir les demandes de ce métier →
            </Link>
          </Card>
        </div>
      </div>
    </>
  );
}
