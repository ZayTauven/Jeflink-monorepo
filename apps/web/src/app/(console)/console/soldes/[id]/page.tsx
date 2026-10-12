import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { CardGrid } from "@/console/cards";
import { consoleGet, type Query } from "@/console/data";
import { Field } from "@/console/forms";
import { ActionForm, Avatar, Flash } from "@/console/kit";
import { balanceLabel } from "@/console/money";
import { Submit } from "@/console/submit";
import { ago, plural } from "@/console/text";
import type { BalanceDetail } from "@/console/types";
import { Card, Kpi, PageHead } from "@/console/ui";
import { formatDate, formatXOF } from "@/lib/format";

type Props = { params: Promise<{ id: string }>; searchParams: Promise<Query> };

export const metadata: Metadata = { title: "Solde d'un pro" };

export default async function BalancePage({ params, searchParams }: Props) {
  const [{ id }, flash] = await Promise.all([params, searchParams]);
  if (!/^\d+$/.test(id)) notFound();
  const here = `/console/soldes/${id}`;
  const b = await consoleGet<BalanceDetail>(here, `balances/${id}/`);
  const label = balanceLabel(b.balance);

  return (
    <>
      <p className="jf-back">
        <Link href="/console/soldes" className="jf-link">
          ← Tous les soldes
        </Link>
      </p>
      <div className="jf-identity">
        <Avatar name={b.pro.name} photo={b.pro.photo} size={64} />
        <PageHead
          title={b.pro.name}
          subtitle={
            <span className="jf-inline">
              <span className={`jf-status ${label.cls}`}>{label.text}</span>
              {b.pro.phone && <a href={`tel:${b.pro.phone}`}>{b.pro.phone}</a>}
              <Link href={`/console/pros/${b.pro.id}`} className="jf-link">
                Fiche pro
              </Link>
            </span>
          }
        />
      </div>
      <Flash ok={flash.ok} erreur={flash.erreur} />

      <div className="ax-dash-grid">
        <Kpi
          label={b.due < 0 ? "Remises à rembourser au pro" : "Net dû par le pro"}
          icon="bi-cash-coin"
          dark
          value={Math.abs(b.due).toLocaleString("fr-FR")}
          unit="F CFA"
          foot={`Commissions moins remises, ${plural(b.missions_done, "mission terminée", "missions terminées")}`}
          className="ax-col--4"
        />
        <Kpi
          label="Déjà réglé"
          icon="bi-check2-circle"
          value={b.settled.toLocaleString("fr-FR")}
          unit="F CFA"
          className="ax-col--4"
        />
        <Kpi
          label={b.balance < 0 ? "Jeflink doit au pro" : "Reste à encaisser"}
          icon="bi-wallet2"
          value={Math.abs(b.balance).toLocaleString("fr-FR")}
          unit="F CFA"
          className="ax-col--4"
        />

        <div className="ax-col--8 jf-stack">
          <Card title="Règlements" eyebrow="Historique">
            {b.settlements.length === 0 ? (
              <p className="jf-muted">Aucun règlement enregistré.</p>
            ) : (
              <ul className="ax-list ax-list--compact">
                {b.settlements.map((st) => (
                  <li key={st.id} className="ax-list__row">
                    <span className="ax-list__content">
                      <span className="ax-list__title">
                        {st.direction_label} · {formatXOF(st.amount)}
                      </span>
                      <span className="ax-list__meta">
                        {st.method_label}
                        {st.reference && ` · réf. ${st.reference}`}
                        {st.note && ` · ${st.note}`} · {formatDate(st.created_at, true)}
                        {st.recorded_by && ` · ${st.recorded_by.name}`}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="Missions terminées" eyebrow="Détail du dû">
            <CardGrid empty="Aucune mission terminée.">
              {b.missions.map((m) => (
                <div key={m.id} className="jf-mini">
                  <Link href={`/console/demandes/${m.id}`} className="jf-link jf-strong">
                    #{m.id} {m.title}
                  </Link>
                  <span className="jf-sub">
                    Devis {formatXOF(m.price)} · commission {formatXOF(m.commission)}
                    {m.discount ? ` · remise ${formatXOF(m.discount)} (${m.coupon})` : ""} ·{" "}
                    {ago(m.updated_at)}
                  </span>
                  <span className="jf-strong ax-num">
                    {m.net < 0 ? "Jeflink doit" : "Le pro doit"} {formatXOF(Math.abs(m.net))}
                  </span>
                </div>
              ))}
            </CardGrid>
          </Card>
        </div>

        <div className="ax-col--4 jf-col-md-full jf-stack">
          <Card title="Enregistrer un règlement" eyebrow="Finance">
            <ActionForm
              endpoint={`/api/console/balances/${b.pro.id}/settle/`}
              back={here}
              ok="Règlement enregistré."
              className="jf-form jf-form--single"
            >
              <Field id="direction" label="Sens">
                <select
                  id="direction"
                  name="direction"
                  className="ax-select"
                  defaultValue={b.balance < 0 ? "to_pro" : "to_jeflink"}
                >
                  <option value="to_jeflink">Le pro a payé Jeflink</option>
                  <option value="to_pro">Jeflink a payé le pro</option>
                </select>
              </Field>
              <Field id="amount" label="Montant (F CFA)" hint="Nombre entier, sans virgule.">
                <input
                  id="amount"
                  name="amount"
                  className="ax-input"
                  inputMode="numeric"
                  required
                  defaultValue={b.balance ? Math.abs(b.balance) : ""}
                />
              </Field>
              <Field id="method" label="Moyen">
                <select id="method" name="method" className="ax-select" defaultValue="wave">
                  <option value="wave">Wave</option>
                  <option value="orange_money">Orange Money</option>
                  <option value="cash">Espèces</option>
                  <option value="transfer">Virement</option>
                </select>
              </Field>
              <Field id="reference" label="Référence" hint="N° de transaction, de reçu…">
                <input id="reference" name="reference" className="ax-input" maxLength={60} />
              </Field>
              <Field id="note" label="Note">
                <input id="note" name="note" className="ax-input" maxLength={200} />
              </Field>
              <div className="jf-form__wide">
                <Submit>Enregistrer</Submit>
              </div>
            </ActionForm>
          </Card>
        </div>
      </div>
    </>
  );
}
