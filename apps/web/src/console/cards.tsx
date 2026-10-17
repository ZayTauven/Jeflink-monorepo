/**
 * Cartes des listes de la console : un élément = une carte sur le fond de la page, comme les
 * litiges. Même trame partout : en-tête (rubrique, titre, statut), contenu, pied (chiffres, actions).
 */
import Link from "next/link";
import type { ReactNode } from "react";

import { ActionButton, Avatar, ReasonAction, Stars } from "./kit";
import { ago, plural } from "./text";
import { targetHref } from "./audit";
import type { AuditRow, ClientRow, ContactRow, ProRow, RequestRow, ReviewRow } from "./types";
import { Status } from "./ui";
import { formatDate, formatRating, formatXOF } from "@/lib/format";

const NBSP = " ";

/**
 * Grille de cartes ; vide → message dans une carte. `clear` : adresse sans les filtres,
 * proposée quand ce sont eux qui vident la liste.
 */
export function CardGrid({
  empty,
  clear,
  children,
}: {
  empty: string;
  clear?: string;
  children: ReactNode[];
}) {
  if (children.length === 0) {
    return (
      <section className="ax-card jf-empty">
        <span className="jf-kpi-icon" aria-hidden="true">
          <i className={`bi ${clear ? "bi-funnel" : "bi-inbox"}`} />
        </span>
        <p className="jf-muted">{empty}</p>
        {clear && (
          <Link href={clear} className="ax-btn ax-btn--secondary ax-btn--sm" scroll={false}>
            Effacer les filtres
          </Link>
        )}
      </section>
    );
  }
  return <div className="jf-cards">{children}</div>;
}

function ItemCard({
  label,
  eyebrow,
  title,
  aside,
  leading,
  children,
  stats,
  actions,
}: {
  label: string;
  eyebrow: ReactNode;
  title: ReactNode;
  aside?: ReactNode;
  leading?: ReactNode;
  children?: ReactNode;
  stats?: [string, ReactNode][];
  actions?: ReactNode;
}) {
  return (
    <article className="ax-card jf-item" aria-label={label}>
      <div className="jf-item__head">
        {leading}
        <div className="jf-item__titles">
          <span className="ax-card__eyebrow">{eyebrow}</span>
          <h2 className="jf-item__title">{title}</h2>
        </div>
        {aside && <div className="jf-item__aside">{aside}</div>}
      </div>
      {children && <div className="jf-item__body">{children}</div>}
      {(stats || actions) && (
        <div className="jf-item__foot">
          {stats && (
            <dl className="jf-item__stats">
              {stats.map(([k, v]) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd className="ax-num">{v}</dd>
                </div>
              ))}
            </dl>
          )}
          {actions && <div className="jf-item__actions">{actions}</div>}
        </div>
      )}
    </article>
  );
}

export function RequestCard({ r }: { r: RequestRow }) {
  return (
    <ItemCard
      label={`Demande ${r.id}`}
      eyebrow={
        <>
          <i className={`bi ${r.trade.icon}`} aria-hidden="true" /> {r.trade.name} · {r.zone.name}
        </>
      }
      title={
        <Link href={`/console/demandes/${r.id}`} className="jf-link">
          #{r.id} {r.title}
        </Link>
      }
      aside={
        <span className="jf-inline jf-inline--end">
          {r.is_urgent && <span className="jf-status jf-status--open">Urgent</span>}
          {r.open_disputes > 0 && (
            <span className="jf-status jf-status--cancelled jf-flag">Litige</span>
          )}
          <Status status={r.status} label={r.status_label} />
        </span>
      }
      stats={[
        [
          "Client",
          <Link key="c" href={`/console/clients/${r.client.id}`} className="jf-link">
            {r.client.name}
          </Link>,
        ],
        [
          "Pro",
          r.pro ? (
            <Link key="p" href={`/console/pros/${r.pro.id}`} className="jf-link">
              {r.pro.name}
            </Link>
          ) : (
            "—"
          ),
        ],
        ["Devis", `${r.quotes_count}/${r.quotes_max}`],
        ["Montant", r.amount === null ? "—" : formatXOF(r.amount)],
        ["Publiée", ago(r.created_at)],
      ]}
    />
  );
}

export function ProCard({ p, back, pending }: { p: ProRow; back: string; pending: boolean }) {
  const a = p.account;
  const state = !a.is_active
    ? { label: "Suspendu", cls: "jf-status--cancelled" }
    : p.is_verified
      ? { label: "Vérifié", cls: "jf-status--done" }
      : { label: "À vérifier", cls: "jf-status--open" };
  return (
    <ItemCard
      label={a.name}
      leading={<Avatar name={a.name} photo={p.photo || a.photo} size={48} />}
      eyebrow={[
        p.trades.join(", ") || "Aucun métier validé",
        p.pending_trades.length > 0 &&
          `à valider${NBSP}: ${p.pending_trades.map((t) => t.name).join(", ")}`,
      ]
        .filter(Boolean)
        .join(" · ")}
      title={
        <Link href={`/console/pros/${a.id}`} className="jf-link">
          {a.name}
        </Link>
      }
      aside={<span className={`jf-status ${state.cls}`}>{state.label}</span>}
      stats={
        pending
          ? [
              ["Inscrit", ago(a.date_joined)],
              ["Téléphone", a.phone || "—"],
              ["Expérience", plural(p.years_experience, "an", "ans")],
            ]
          : [
              ["Missions", String(p.missions_done)],
              [
                "Note",
                p.rating.count
                  ? `${formatRating(p.rating.average)}/5 (${p.rating.count})`
                  : "Pas encore noté",
              ],
              ["Inscrit", ago(a.date_joined)],
            ]
      }
      actions={
        pending &&
        a.is_active && (
          <>
            {p.has_accepted_id ? (
              <ActionButton
                endpoint={`/api/console/pros/${a.id}/verify/`}
                back={back}
                ok={`Pro vérifié${NBSP}: il peut envoyer des devis.`}
                label="Vérifier"
              />
            ) : (
              // Pas encore de pièce d'identité acceptée : on l'examine sur la fiche.
              <Link href={`/console/pros/${a.id}`} className="ax-btn ax-btn--primary ax-btn--sm">
                Examiner les documents
              </Link>
            )}
            <ReasonAction
              endpoint={`/api/console/pros/${a.id}/reject/`}
              back={back}
              ok={`Refus enregistré${NBSP}: le pro voit le motif dans son espace.`}
              label="Refuser…"
              title="Refuser la vérification"
              subject={a.name}
              confirm="Confirmer le refus"
              placeholder={`Ce qui manque, ex.${NBSP}: pièce d'identité illisible.`}
            />
          </>
        )
      }
    >
      {p.headline && <p className="jf-prose">{p.headline}</p>}
      {p.verification_note && (
        <p className="jf-flag">
          Refusé{NBSP}: {p.verification_note}
        </p>
      )}
      {!a.is_active && (
        <p className="jf-flag">
          Suspendu{NBSP}: {a.suspension_reason}
        </p>
      )}
    </ItemCard>
  );
}

export function ClientCard({ c }: { c: ClientRow }) {
  return (
    <ItemCard
      label={c.name}
      leading={<Avatar name={c.name} photo={c.photo} size={48} />}
      eyebrow={c.email}
      title={
        <Link href={`/console/clients/${c.id}`} className="jf-link">
          {c.name}
        </Link>
      }
      aside={
        <span className={`jf-status ${c.is_active ? "jf-status--done" : "jf-status--cancelled"}`}>
          {c.is_active ? "Actif" : "Suspendu"}
        </span>
      }
      stats={[
        ["Demandes", String(c.requests_count)],
        ["Missions terminées", formatXOF(c.spent)],
        ["Dernière demande", c.last_request_at ? ago(c.last_request_at) : "—"],
        ["Téléphone", c.phone || "—"],
      ]}
    >
      {!c.is_active && (
        <p className="jf-flag">
          Suspendu{NBSP}: {c.suspension_reason}
        </p>
      )}
    </ItemCard>
  );
}

export function ReviewCard({ r, back }: { r: ReviewRow; back: string }) {
  return (
    <ItemCard
      label={`Avis ${r.rating} sur 5`}
      eyebrow={
        <>
          {r.request.trade} ·{" "}
          <Link href={`/console/demandes/${r.request.id}`} className="jf-link">
            #{r.request.id}
          </Link>{" "}
          · {ago(r.created_at)}
        </>
      }
      title={<Stars rating={r.rating} />}
      aside={r.is_hidden && <span className="jf-status jf-status--cancelled">Masqué</span>}
      stats={[
        [
          "Client",
          <Link key="c" href={`/console/clients/${r.client.id}`} className="jf-link">
            {r.client.name}
          </Link>,
        ],
        [
          "Pro",
          r.pro ? (
            <Link key="p" href={`/console/pros/${r.pro.id}`} className="jf-link">
              {r.pro.name}
            </Link>
          ) : (
            "—"
          ),
        ],
      ]}
      actions={
        r.is_hidden ? (
          <ActionButton
            endpoint={`/api/console/reviews/${r.id}/show/`}
            back={back}
            ok={`Avis rétabli${NBSP}: il compte de nouveau dans la note du pro.`}
            label="Rétablir"
            variant="ax-btn ax-btn--secondary ax-btn--sm"
          />
        ) : (
          <ReasonAction
            endpoint={`/api/console/reviews/${r.id}/hide/`}
            back={back}
            ok={`Avis masqué${NBSP}: il sort du site et de la note du pro.`}
            label="Masquer…"
            title="Masquer l'avis"
            subject={`${r.rating}/5 de ${r.client.name}${r.pro ? ` pour ${r.pro.name}` : ""}`}
            confirm="Masquer l'avis"
            placeholder={`Ex.${NBSP}: insultes, numéro de téléphone dans le texte.`}
          />
        )
      }
    >
      <p className="jf-prose">{r.comment ? `«${NBSP}${r.comment}${NBSP}»` : "Sans commentaire."}</p>
      {r.is_hidden && (
        <p className="jf-flag">
          Motif{NBSP}: {r.hidden_reason}
        </p>
      )}
    </ItemCard>
  );
}

export function MessageCard({ m, back }: { m: ContactRow; back: string }) {
  return (
    <ItemCard
      label={`Message de ${m.name}`}
      eyebrow={`Reçu ${ago(m.created_at)}`}
      title={m.name}
      aside={m.is_handled && <span className="jf-status jf-status--done">Traité</span>}
      stats={[
        [
          "Email",
          <a
            key="e"
            className="jf-link"
            href={`mailto:${m.email}?subject=${encodeURIComponent("Votre message à Jeflink")}`}
          >
            {m.email}
          </a>,
        ],
        ...(m.is_handled && m.handled_by
          ? ([
              ["Traité par", `${m.handled_by.name}${m.handled_at ? `, ${ago(m.handled_at)}` : ""}`],
            ] as [string, ReactNode][])
          : []),
      ]}
      actions={
        m.is_handled ? (
          <ActionButton
            endpoint={`/api/console/messages/${m.id}/reopen/`}
            back={back}
            ok="Message remis à traiter."
            label="Rouvrir"
            variant="ax-btn ax-btn--ghost ax-btn--sm"
          />
        ) : (
          <ActionButton
            endpoint={`/api/console/messages/${m.id}/handle/`}
            back={back}
            ok="Message marqué comme traité."
            label="Marquer traité"
          />
        )
      }
    >
      <p className="jf-prose">{m.message}</p>
    </ItemCard>
  );
}

export function AuditCard({ row }: { row: AuditRow }) {
  const href = targetHref(row);
  return (
    <ItemCard
      label={row.action_label}
      eyebrow={`${formatDate(row.created_at, true)} · ${row.actor?.name ?? "Équipe"}`}
      title={row.action_label}
    >
      <p className="jf-prose">
        <span className="jf-sub">Concerne</span>
        {href ? (
          <Link href={href} className="jf-link jf-strong">
            {row.target_label}
          </Link>
        ) : (
          <span className="jf-strong">{row.target_label}</span>
        )}
      </p>
      {row.details && (
        <p className="jf-prose">
          <span className="jf-sub">Précisions</span>
          {row.details}
        </p>
      )}
    </ItemCard>
  );
}
