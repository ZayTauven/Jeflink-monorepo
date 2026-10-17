import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { AuditTrail } from "@/console/audit";
import { DisputeCard, RequestTable } from "@/console/blocks";
import { consoleGet, type Query } from "@/console/data";
import { ActionButton, Avatar, Facts, Flash, ReasonAction, Stars } from "@/console/kit";
import { ago, plural } from "@/console/text";
import type { ProDetail } from "@/console/types";
import { Card, Kpi, PageHead } from "@/console/ui";
import { formatDate, formatRating } from "@/lib/format";

const DOC_STATUS = {
  pending: "jf-status--open",
  accepted: "jf-status--done",
  rejected: "jf-status--cancelled",
};

type Props = { params: Promise<{ id: string }>; searchParams: Promise<Query> };

export async function generateMetadata(): Promise<Metadata> {
  return { title: "Fiche pro" };
}

export default async function ProPage({ params, searchParams }: Props) {
  const [{ id }, flash] = await Promise.all([params, searchParams]);
  if (!/^\d+$/.test(id)) notFound();
  const here = `/console/pros/${id}`;
  const p = await consoleGet<ProDetail>(here, `pros/${id}/`);
  const a = p.account;
  const endpoint = (action: string) => `/api/console/pros/${a.id}/${action}/`;
  const acceptance = p.stats.quotes_sent
    ? Math.round((p.stats.quotes_accepted / p.stats.quotes_sent) * 100)
    : null;
  const state = !a.is_active
    ? { label: "Suspendu", cls: "jf-status--cancelled" }
    : p.is_verified
      ? { label: "Vérifié", cls: "jf-status--done" }
      : { label: "À vérifier", cls: "jf-status--open" };

  return (
    <>
      <p className="jf-back">
        <Link href="/console/pros" className="jf-link">
          ← Tous les pros
        </Link>
      </p>
      <div className="jf-identity">
        <Avatar name={a.name} photo={p.photo || a.photo} size={64} />
        <PageHead
          title={a.name}
          subtitle={
            <span className="jf-inline">
              <span className={`jf-status ${state.cls}`}>{state.label}</span>
              <span>
                {p.trades.join(", ") || "Aucun métier"}
                {p.headline && ` · ${p.headline}`}
              </span>
            </span>
          }
        />
      </div>
      <Flash ok={flash.ok} erreur={flash.erreur} />
      {!a.is_active && (
        <div className="ax-alert ax-alert--warning mb-6" role="status">
          <div className="ax-alert__content">
            <p className="ax-alert__message">
              Compte suspendu : {a.suspension_reason}. Le pro ne peut plus se connecter.
            </p>
          </div>
        </div>
      )}

      <div className="ax-dash-grid">
        <Kpi
          label="Missions terminées"
          icon="bi-patch-check"
          dark
          value={String(p.missions_done)}
        />
        <Kpi
          label="Devis acceptés"
          icon="bi-percent"
          value={acceptance === null ? "—" : String(acceptance)}
          unit={acceptance === null ? undefined : "%"}
          foot={`${p.stats.quotes_accepted} sur ${plural(p.stats.quotes_sent, "devis envoyé", "devis envoyés")}`}
        />
        <Kpi
          label="Volume réalisé"
          icon="bi-cash-coin"
          value={p.stats.volume.toLocaleString("fr-FR")}
          unit="F CFA"
          foot="Missions terminées"
        />
        <Kpi
          label="Note"
          icon="bi-star-half"
          value={formatRating(p.rating.average)}
          unit={p.rating.average === null ? undefined : "/ 5"}
          foot={plural(p.rating.count, "avis visible", "avis visibles")}
        />

        <div className="ax-col--8 jf-stack">
          <Card title="Missions récentes" eyebrow="Activité">
            <RequestTable rows={p.missions} empty="Aucune mission pour l'instant." />
          </Card>
          <Card title="Avis reçus" eyebrow="Clients">
            {p.reviews.length === 0 ? (
              <p className="jf-muted">Aucun avis.</p>
            ) : (
              <ul className="ax-list ax-list--compact">
                {p.reviews.map((r) => (
                  <li key={r.id} className="ax-list__row">
                    <span className="ax-list__content">
                      <span className="ax-list__title jf-inline">
                        <Stars rating={r.rating} />
                        {r.is_hidden && (
                          <span className="jf-status jf-status--cancelled">Masqué</span>
                        )}
                      </span>
                      <span className="ax-list__meta">
                        {r.comment ? `« ${r.comment} »` : "Sans commentaire"} · {r.client.name} ·{" "}
                        {ago(r.created_at)}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          {p.disputes.map((d) => (
            <DisputeCard key={d.id} dispute={d} back={here} />
          ))}
        </div>

        <div className="ax-col--4 jf-col-md-full jf-stack">
          <Card title="Compte" eyebrow="Contact">
            <Facts
              items={[
                ["Email", <a href={`mailto:${a.email}`}>{a.email}</a>],
                ["Téléphone", a.phone && <a href={`tel:${a.phone}`}>{a.phone}</a>],
                ["Joignable", `${a.contact_pref} · ${a.contact_hours}`],
                ["Expérience", plural(p.years_experience, "an", "ans")],
                ["Quartiers", p.zones.join(", ") || "Tout Dakar"],
                ["Inscrit", formatDate(a.date_joined)],
                ["Dernière connexion", a.last_login ? ago(a.last_login) : "Jamais"],
                ["Vérifié le", p.verified_at && formatDate(p.verified_at)],
              ]}
            />
            {p.bio && <p className="jf-prose mt-3">{p.bio}</p>}
          </Card>

          <Card title="Documents" eyebrow="Vérification">
            {p.documents.length === 0 ? (
              <p className="jf-muted">
                Aucun document. Le pro envoie sa pièce d'identité depuis son profil.
              </p>
            ) : (
              <ul className="jf-stack jf-stack--tight" aria-label="Documents du pro">
                {p.documents.map((d) => (
                  <li key={d.id} className="jf-doc">
                    <div className="jf-inline jf-inline--between">
                      <b>{d.kind_label}</b>
                      <span className={`jf-status ${DOC_STATUS[d.status]}`}>{d.status_label}</span>
                    </div>
                    <p className="jf-muted">
                      Envoyé {ago(d.created_at)} ·{" "}
                      <a
                        className="jf-link"
                        href={`/documents/${d.id}`}
                        target="_blank"
                        rel="noopener"
                      >
                        {d.content_type === "application/pdf"
                          ? "Télécharger le PDF"
                          : "Ouvrir la photo"}
                      </a>
                    </p>
                    {d.note && <p className="jf-flag">Refusé : {d.note}</p>}
                    {d.status === "pending" && (
                      <div className="jf-inline">
                        <ActionButton
                          endpoint={`/api/console/documents/${d.id}/accept/`}
                          back={here}
                          ok="Document accepté."
                          label="Accepter"
                          variant="ax-btn ax-btn--primary ax-btn--sm"
                        />
                        <ReasonAction
                          endpoint={`/api/console/documents/${d.id}/reject/`}
                          back={here}
                          ok="Document refusé : le pro voit le motif dans son profil."
                          label="Refuser…"
                          title="Refuser le document"
                          subject={`${d.kind_label} de ${a.name}`}
                          confirm="Refuser"
                          placeholder="Ex. : photo floue, pièce expirée."
                          danger={false}
                        />
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Actions" eyebrow="Équipe">
            <div className="jf-stack jf-stack--tight">
              {p.verification_note && (
                <p className="jf-flag">Dernier refus : {p.verification_note}</p>
              )}
              {a.is_active && !p.is_verified && !p.has_accepted_id && (
                <p className="jf-flag">
                  Pour vérifier ce pro, acceptez d'abord sa pièce d'identité (Documents), après
                  l'avoir comparée à la personne au téléphone.
                </p>
              )}
              {a.is_active && !p.is_verified && p.has_accepted_id && (
                <ActionButton
                  endpoint={endpoint("verify")}
                  back={here}
                  ok="Pro vérifié : il peut envoyer des devis."
                  label="Vérifier ce pro"
                  variant="ax-btn ax-btn--primary"
                />
              )}
              {a.is_active && (
                <ReasonAction
                  endpoint={endpoint("reject")}
                  back={here}
                  ok={`${p.is_verified ? "Vérification retirée" : "Refus enregistré"} : le pro voit le motif dans son espace.`}
                  label={p.is_verified ? "Retirer la vérification…" : "Refuser…"}
                  title={p.is_verified ? "Retirer la vérification" : "Refuser la vérification"}
                  subject={a.name}
                  confirm="Confirmer"
                  placeholder="Ce qui manque, ex. : attestation de formation."
                  danger={false}
                />
              )}
              {a.is_active ? (
                <ReasonAction
                  endpoint={endpoint("suspend")}
                  back={here}
                  ok="Compte suspendu : le pro est déconnecté."
                  label="Suspendre le compte…"
                  subject={a.name}
                  confirm="Confirmer la suspension"
                  placeholder="Ex. : deux litiges graves, en attente d'explications."
                />
              ) : (
                <ActionButton
                  endpoint={endpoint("reactivate")}
                  back={here}
                  ok="Compte réactivé."
                  label="Réactiver le compte"
                  variant="ax-btn ax-btn--secondary"
                />
              )}
            </div>
          </Card>

          <AuditTrail here={here} target="pro" id={a.id} />
        </div>
      </div>
    </>
  );
}
