import type { Metadata } from "next";
import Link from "next/link";

import { CardGrid } from "@/console/cards";
import { consoleGet, type Query } from "@/console/data";
import { Avatar, Flash } from "@/console/kit";
import { balanceLabel } from "@/console/money";
import { plural } from "@/console/text";
import type { BalanceRow } from "@/console/types";
import { Kpi, PageHead } from "@/console/ui";
import { formatXOF } from "@/lib/format";

export const metadata: Metadata = { title: "Soldes des pros" };

const BASE = "/console/soldes";
const NBSP = " ";

export default async function BalancesPage({ searchParams }: { searchParams: Promise<Query> }) {
  const params = await searchParams;
  const data = await consoleGet<{
    results: BalanceRow[];
    totals: { owed_by_pros: number; owed_to_pros: number };
  }>(BASE, "balances/");

  return (
    <>
      <PageHead
        title="Soldes des pros"
        subtitle={`Pour chaque mission terminée, le pro doit la commission à Jeflink et Jeflink lui doit la remise du code promo. Enregistrez ici chaque règlement reçu ou versé.`}
      />
      <Flash ok={params.ok} erreur={params.erreur} />
      <div className="ax-dash-grid mb-6">
        <Kpi
          label="À encaisser auprès des pros"
          icon="bi-wallet2"
          dark
          value={data.totals.owed_by_pros.toLocaleString("fr-FR")}
          unit="F CFA"
          className="ax-col--6"
        />
        <Kpi
          label="À reverser aux pros"
          icon="bi-arrow-left-right"
          value={data.totals.owed_to_pros.toLocaleString("fr-FR")}
          unit="F CFA"
          foot={`Remises de codes promo${NBSP}: Jeflink les doit au pro`}
          className="ax-col--6"
        />
      </div>
      <CardGrid empty="Aucune mission terminée pour l'instant.">
        {data.results.map((r) => {
          const label = balanceLabel(r.balance);
          return (
            <article key={r.pro.id} className="ax-card jf-item" aria-label={r.pro.name}>
              <div className="jf-item__head">
                <Avatar name={r.pro.name} photo={r.pro.photo} size={48} />
                <div className="jf-item__titles">
                  <span className="ax-card__eyebrow">
                    {plural(r.missions_done, "mission terminée", "missions terminées")}
                  </span>
                  <h2 className="jf-item__title">
                    <Link href={`${BASE}/${r.pro.id}`} className="jf-link">
                      {r.pro.name}
                    </Link>
                  </h2>
                </div>
                <div className="jf-item__aside">
                  <span className={`jf-status ${label.cls}`}>{label.text}</span>
                </div>
              </div>
              <div className="jf-item__foot">
                <dl className="jf-item__stats">
                  <div>
                    <dt>Net dû par le pro</dt>
                    <dd className="ax-num">{formatXOF(r.due)}</dd>
                  </div>
                  <div>
                    <dt>Déjà réglé</dt>
                    <dd className="ax-num">{formatXOF(r.settled)}</dd>
                  </div>
                </dl>
                <div className="jf-item__actions">
                  <Link
                    href={`${BASE}/${r.pro.id}`}
                    className="ax-btn ax-btn--secondary ax-btn--sm"
                  >
                    Détail et règlement
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
