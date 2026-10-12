import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { AuditTrail } from "@/console/audit";
import { DisputeCard, RequestTable } from "@/console/blocks";
import { consoleGet, type Query } from "@/console/data";
import { ActionButton, Avatar, Facts, Flash, ReasonAction, Stars } from "@/console/kit";
import { ago } from "@/console/text";
import type { ClientDetail } from "@/console/types";
import { Card, Kpi, PageHead } from "@/console/ui";
import { formatDate } from "@/lib/format";

type Props = { params: Promise<{ id: string }>; searchParams: Promise<Query> };

export const metadata: Metadata = { title: "Fiche client" };

export default async function ClientPage({ params, searchParams }: Props) {
  const [{ id }, flash] = await Promise.all([params, searchParams]);
  if (!/^\d+$/.test(id)) notFound();
  const here = `/console/clients/${id}`;
  const c = await consoleGet<ClientDetail>(here, `clients/${id}/`);
  const endpoint = (action: string) => `/api/console/clients/${c.id}/${action}/`;

  return (
    <>
      <p className="jf-back">
        <Link href="/console/clients" className="jf-link">
          ← Tous les clients
        </Link>
      </p>
      <div className="jf-identity">
        <Avatar name={c.name} photo={c.photo} size={64} />
        <PageHead
          title={c.name}
          subtitle={
            <span className="jf-inline">
              <span
                className={`jf-status ${c.is_active ? "jf-status--done" : "jf-status--cancelled"}`}
              >
                {c.is_active ? "Actif" : "Suspendu"}
              </span>
              <span>Client depuis le {formatDate(c.date_joined)}</span>
            </span>
          }
        />
      </div>
      <Flash ok={flash.ok} erreur={flash.erreur} />
      {!c.is_active && (
        <div className="ax-alert ax-alert--warning mb-6" role="status">
          <div className="ax-alert__content">
            <p className="ax-alert__message">
              Compte suspendu : {c.suspension_reason}. Le client ne peut plus se connecter.
            </p>
          </div>
        </div>
      )}

      <div className="ax-dash-grid">
        <Kpi
          label="Demandes publiées"
          icon="bi-inbox"
          dark
          value={String(c.requests_count)}
          className="ax-col--4"
        />
        <Kpi
          label="Missions terminées"
          icon="bi-cash-coin"
          value={c.spent.toLocaleString("fr-FR")}
          unit="F CFA"
          foot="Devis acceptés, missions terminées"
          className="ax-col--4"
        />
        <Kpi
          label="Dernière demande"
          icon="bi-clock-history"
          value={c.last_request_at ? ago(c.last_request_at) : "—"}
          className="ax-col--4"
        />

        <div className="ax-col--8 jf-stack">
          <Card title="Demandes" eyebrow="Historique">
            <RequestTable rows={c.requests} empty="Ce client n'a encore rien demandé." />
          </Card>
          <Card title="Avis laissés" eyebrow="Après mission">
            {c.reviews.length === 0 ? (
              <p className="jf-muted">Aucun avis.</p>
            ) : (
              <ul className="ax-list ax-list--compact">
                {c.reviews.map((r) => (
                  <li key={r.id} className="ax-list__row">
                    <span className="ax-list__content">
                      <span className="ax-list__title">
                        <Stars rating={r.rating} /> pour {r.pro?.name ?? "un pro"}
                      </span>
                      <span className="ax-list__meta">
                        {r.comment ? `« ${r.comment} »` : "Sans commentaire"} · {ago(r.created_at)}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          {c.disputes.map((d) => (
            <DisputeCard key={d.id} dispute={d} back={here} />
          ))}
        </div>

        <div className="ax-col--4 jf-col-md-full jf-stack">
          <Card title="Compte" eyebrow="Contact">
            <Facts
              items={[
                ["Email", <a href={`mailto:${c.email}`}>{c.email}</a>],
                ["Téléphone", c.phone && <a href={`tel:${c.phone}`}>{c.phone}</a>],
                ["Dernière connexion", c.last_login ? ago(c.last_login) : "Jamais"],
              ]}
            />
          </Card>
          <Card title="Actions" eyebrow="Équipe">
            {c.is_active ? (
              <ReasonAction
                endpoint={endpoint("suspend")}
                back={here}
                ok="Compte suspendu : le client est déconnecté."
                label="Suspendre le compte…"
                confirm="Confirmer la suspension"
                placeholder="Ex. : fausses demandes répétées."
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
          </Card>
          <AuditTrail here={here} target="client" id={c.id} />
        </div>
      </div>
    </>
  );
}
