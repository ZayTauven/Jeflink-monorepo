import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { DisputeCard } from "@/console/blocks";
import { consoleGet, type Query } from "@/console/data";
import { ActionForm, Facts, Flash, ReasonAction, Stars } from "@/console/kit";
import { Submit } from "@/console/submit";
import { ago } from "@/console/text";
import type { Contact, RequestDetail } from "@/console/types";
import { Card, PageHead, Status } from "@/console/ui";
import { formatDate, formatXOF } from "@/lib/format";

type Props = { params: Promise<{ id: string }>; searchParams: Promise<Query> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  return { title: `Demande n° ${(await params).id}` };
}

const REASONS: [string, string][] = [
  ["no_show", "Pro absent ou très en retard"],
  ["quality", "Travail mal fait ou inachevé"],
  ["price", "Prix différent du devis"],
  ["behaviour", "Comportement"],
  ["damage", "Dégât chez le client"],
  ["payment", "Paiement non reçu"],
  ["other", "Autre"],
];

export default async function RequestDetailPage({ params, searchParams }: Props) {
  const [{ id }, flash] = await Promise.all([params, searchParams]);
  if (!/^\d+$/.test(id)) notFound();
  const here = `/console/demandes/${id}`;
  const r = await consoleGet<RequestDetail>(here, `requests/${id}/`);
  const endpoint = (action: string) => `/api/console/requests/${r.id}/${action}/`;

  return (
    <>
      <p className="jf-back">
        <Link href="/console/demandes" className="jf-link">
          ← Toutes les demandes
        </Link>
      </p>
      <PageHead
        title={`#${r.id} ${r.title}`}
        subtitle={
          <span className="jf-inline">
            <Status status={r.status} label={r.status_label} />
            {r.is_urgent && <span className="jf-status jf-status--open">Urgent</span>}
            <span>
              <i className={`bi ${r.trade.icon}`} aria-hidden="true" /> {r.trade.name} ·{" "}
              {r.zone.name} · publiée le {formatDate(r.created_at, true)}
            </span>
          </span>
        }
      />
      <Flash ok={flash.ok} erreur={flash.erreur} />

      <div className="ax-dash-grid">
        <div className="ax-col--8 jf-stack">
          <Card title="La demande" eyebrow="Description">
            <p className="jf-prose">{r.description}</p>
            <Facts
              items={[
                ["Repère", r.landmark],
                ["Date souhaitée", r.preferred_date && formatDate(r.preferred_date)],
                ["Dernière mise à jour", ago(r.updated_at)],
              ]}
            />
          </Card>

          <Card title={`Devis (${r.quotes.length}/3)`} eyebrow="Prix">
            {r.quotes.length === 0 ? (
              <p className="jf-muted">Aucun devis reçu.</p>
            ) : (
              <div className="ax-table-wrap">
                <table className="ax-table ax-table--compact">
                  <thead>
                    <tr>
                      <th scope="col">Pro</th>
                      <th scope="col">Message</th>
                      <th scope="col" style={{ textAlign: "end" }}>
                        Montant
                      </th>
                      <th scope="col">Statut</th>
                    </tr>
                  </thead>
                  <tbody>
                    {r.quotes.map((q) => (
                      <tr key={q.id}>
                        <td>
                          <Link href={`/console/pros/${q.pro.id}`} className="jf-link">
                            {q.pro.name}
                          </Link>
                          <span className="jf-sub">{ago(q.created_at)}</span>
                        </td>
                        <td>{q.message || "—"}</td>
                        <td className="ax-num jf-strong jf-nowrap" style={{ textAlign: "end" }}>
                          {formatXOF(q.amount)}
                        </td>
                        <td>
                          <span
                            className={`jf-status ${q.status === "accepted" ? "jf-status--done" : q.status === "declined" ? "jf-status--cancelled" : "jf-status--open"}`}
                          >
                            {q.status_label}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {r.disputes.map((d) => (
            <DisputeCard key={d.id} dispute={d} back={here} showRequest={false} />
          ))}

          {r.review && (
            <Card title="Avis du client" eyebrow="Après mission">
              <p className="jf-inline">
                <Stars rating={r.review.rating} />
                {r.review.is_hidden && (
                  <span className="jf-status jf-status--cancelled">
                    Masqué : {r.review.hidden_reason}
                  </span>
                )}
              </p>
              <p className="jf-prose">{r.review.comment || "Sans commentaire."}</p>
              <Link href="/console/avis" className="jf-link">
                Modérer dans Avis →
              </Link>
            </Card>
          )}

          <Card title="Historique" eyebrow="Journal de la demande">
            <ol className="ax-timeline">
              {r.events.map((e) => (
                <li
                  key={e.id}
                  className={`ax-timeline__item${e.status === "done" ? " ax-timeline__item--success" : e.status === "cancelled" ? " ax-timeline__item--danger" : ""}`}
                >
                  <span className="ax-timeline__marker" aria-hidden="true">
                    <i className="bi bi-dot" />
                  </span>
                  <div className="ax-timeline__content">
                    <p className="ax-timeline__title">{e.note}</p>
                    <span className="ax-timeline__time">
                      {formatDate(e.created_at, true)}
                      {e.actor && ` · ${e.actor.name}`}
                    </span>
                  </div>
                </li>
              ))}
            </ol>
          </Card>
        </div>

        <div className="ax-col--4 jf-col-md-full jf-stack">
          <PartyCard title="Client" person={r.client} href={`/console/clients/${r.client.id}`} />
          {r.pro ? (
            <PartyCard title="Pro réservé" person={r.pro} href={`/console/pros/${r.pro.id}`} />
          ) : null}
          {r.amount !== null && (
            <Card title={formatXOF(r.amount)} eyebrow="Devis accepté">
              <p className="jf-muted">Payé au pro sur place (démo : pas de paiement en ligne).</p>
            </Card>
          )}

          <Card title="Note interne" eyebrow="Équipe seulement">
            <ActionForm endpoint={endpoint("note")} back={here} ok="Note enregistrée.">
              <label className="ax-visually-hidden" htmlFor="note">
                Note interne
              </label>
              <textarea
                id="note"
                name="note"
                className="ax-textarea"
                rows={4}
                maxLength={2000}
                defaultValue={r.staff_note}
                placeholder="Ex. : client rappelé le 12/10, il préfère un passage le matin."
              />
              <div className="mt-3">
                <Submit className="ax-btn ax-btn--secondary ax-btn--sm">Enregistrer la note</Submit>
              </div>
            </ActionForm>
          </Card>

          {(r.can_open_dispute || r.can_cancel) && (
            <Card title="Actions" eyebrow="Équipe">
              <div className="jf-stack jf-stack--tight">
                {r.can_open_dispute && (
                  <details className="jf-reason">
                    <summary className="ax-btn ax-btn--sm ax-btn--secondary">
                      Ouvrir un litige…
                    </summary>
                    <ActionForm
                      endpoint={endpoint("disputes")}
                      back={here}
                      ok="Litige ouvert."
                      className="jf-reason__form"
                    >
                      <label className="ax-field__label" htmlFor="dispute-reason">
                        Motif
                      </label>
                      <select
                        id="dispute-reason"
                        name="reason"
                        className="ax-select"
                        required
                        defaultValue=""
                      >
                        <option value="" disabled>
                          Choisir…
                        </option>
                        {REASONS.map(([v, l]) => (
                          <option key={v} value={v}>
                            {l}
                          </option>
                        ))}
                      </select>
                      <label className="ax-field__label" htmlFor="dispute-description">
                        Ce que dit la personne qui appelle
                      </label>
                      <textarea
                        id="dispute-description"
                        name="description"
                        className="ax-textarea"
                        rows={3}
                        required
                        maxLength={2000}
                      />
                      <Submit className="ax-btn ax-btn--sm ax-btn--primary">
                        Ouvrir le litige
                      </Submit>
                    </ActionForm>
                  </details>
                )}
                {r.can_cancel && (
                  <ReasonAction
                    endpoint={endpoint("cancel")}
                    back={here}
                    ok="Demande annulée."
                    label="Annuler la demande…"
                    confirm="Confirmer l'annulation"
                    placeholder="Ex. : doublon de la demande #12, client prévenu."
                  />
                )}
              </div>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}

function PartyCard({ title, person, href }: { title: string; person: Contact; href: string }) {
  return (
    <Card title={person.name} eyebrow={title}>
      <Facts
        items={[
          ["Email", <a href={`mailto:${person.email}`}>{person.email}</a>],
          ["Téléphone", person.phone && <a href={`tel:${person.phone}`}>{person.phone}</a>],
        ]}
      />
      <Link href={href} className="jf-link">
        Voir la fiche →
      </Link>
    </Card>
  );
}
