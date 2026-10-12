/**
 * Briques des rubriques de la console (Server Components) : message de retour, onglets,
 * pagination, avatars, étoiles et formulaires d'action branchés sur `consoleAction`.
 */
import Link from "next/link";
import type { ReactNode } from "react";

import { consoleAction } from "./actions";
import { Announce } from "./announce";
import { qs, type Query } from "./data";
import { Submit } from "./submit";

/** Message après une action (?ok= / ?erreur=), annoncé aux lecteurs d'écran. */
export function Flash({ ok, erreur }: { ok?: string; erreur?: string }) {
  if (erreur) {
    return (
      <Announce className="ax-alert ax-alert--danger mb-6" role="alert">
        <i className="bi bi-exclamation-triangle ax-alert__icon" aria-hidden="true" />
        <div className="ax-alert__content">
          <p className="ax-alert__message">{erreur}</p>
        </div>
      </Announce>
    );
  }
  if (!ok) return null;
  return (
    <Announce className="ax-alert ax-alert--success mb-6" role="status">
      <i className="bi bi-check2-circle ax-alert__icon" aria-hidden="true" />
      <div className="ax-alert__content">
        <p className="ax-alert__message">{ok}</p>
      </div>
    </Announce>
  );
}

export type Tab = { value: string; label: string; count?: number };

/** Onglets en liens (filtre d'un paramètre de l'URL), avec compteurs. */
export function Tabs({
  base,
  params,
  name,
  tabs,
  label,
}: {
  base: string;
  params: Query;
  name: string;
  tabs: Tab[];
  label: string;
}) {
  const current = params[name] ?? "";
  return (
    <nav className="ax-tabs ax-tabs--pill mb-5" aria-label={label}>
      <div className="ax-tabs__list jf-tabs-list">
        {tabs.map((t) => {
          const active = t.value === current;
          return (
            <Link
              key={t.value || "all"}
              href={`${base}${qs(params, { [name]: t.value || undefined, page: undefined })}`}
              className={`ax-tabs__tab${active ? " is-active" : ""}`}
              aria-current={active ? "page" : undefined}
            >
              <span>{t.label}</span>
              {t.count !== undefined && (
                <span className="ax-badge ax-badge--neutral ax-badge--pill ax-badge--sm ax-num ax-tabs__badge">
                  {t.count}
                </span>
              )}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

const PAGE_SIZE = 20;

export function Pager({ count, base, params }: { count: number; base: string; params: Query }) {
  const pages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  const page = Math.min(pages, Math.max(1, Number(params.page) || 1));
  const at = (p: number) => `${base}${qs(params, { page: p > 1 ? String(p) : undefined })}`;
  return (
    <div className="jf-pager">
      <span className="ax-pagination__summary">
        {count === 0
          ? "Aucun résultat"
          : `${(page - 1) * PAGE_SIZE + 1}–${Math.min(page * PAGE_SIZE, count)} sur ${count}`}
      </span>
      {pages > 1 && (
        <nav className="ax-pagination" aria-label="Pages">
          {page > 1 ? (
            <Link className="ax-pagination__prev" href={at(page - 1)} aria-label="Page précédente">
              <i className="bi bi-chevron-left" aria-hidden="true" />
            </Link>
          ) : (
            <span className="ax-pagination__prev" aria-hidden="true">
              <i className="bi bi-chevron-left" />
            </span>
          )}
          {page < pages ? (
            <Link className="ax-pagination__next" href={at(page + 1)} aria-label="Page suivante">
              <i className="bi bi-chevron-right" aria-hidden="true" />
            </Link>
          ) : (
            <span className="ax-pagination__next" aria-hidden="true">
              <i className="bi bi-chevron-right" />
            </span>
          )}
        </nav>
      )}
    </div>
  );
}

export function Avatar({
  name,
  photo,
  size = 36,
}: {
  name: string;
  photo?: string;
  size?: number;
}) {
  if (photo) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img className="ax-avatar" src={photo} alt="" width={size} height={size} />;
  }
  const letters = name
    .split(" ")
    .filter(Boolean)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return (
    <span
      className="ax-avatar jf-initials"
      style={{ inlineSize: size, blockSize: size }}
      aria-hidden="true"
    >
      {letters}
    </span>
  );
}

export function Stars({ rating }: { rating: number }) {
  return (
    <span className="jf-stars" role="img" aria-label={`Note : ${rating} sur 5`}>
      {"★".repeat(rating)}
      <span className="jf-stars__off">{"★".repeat(5 - rating)}</span>
    </span>
  );
}

/** Formulaire d'action de la console (POST via l'action serveur, retour sur `back`). */
export function ActionForm({
  endpoint,
  back,
  ok,
  className,
  children,
}: {
  endpoint: string;
  back: string;
  ok: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <form action={consoleAction} className={className}>
      <input type="hidden" name="_endpoint" value={endpoint} />
      <input type="hidden" name="_back" value={back} />
      <input type="hidden" name="_ok" value={ok} />
      {children}
    </form>
  );
}

/** Action immédiate (un bouton). */
export function ActionButton({
  endpoint,
  back,
  ok,
  label,
  variant = "ax-btn ax-btn--primary ax-btn--sm",
}: {
  endpoint: string;
  back: string;
  ok: string;
  label: string;
  variant?: string;
}) {
  return (
    <ActionForm endpoint={endpoint} back={back} ok={ok}>
      <Submit className={variant}>{label}</Submit>
    </ActionForm>
  );
}

/**
 * Action qui demande un motif (suspendre, refuser, masquer, annuler) : le formulaire se déplie,
 * le motif est obligatoire et sert de confirmation.
 */
export function ReasonAction({
  endpoint,
  back,
  ok,
  label,
  confirm,
  field = "reason",
  placeholder,
  danger = true,
}: {
  endpoint: string;
  back: string;
  ok: string;
  label: string;
  confirm: string;
  field?: string;
  placeholder: string;
  danger?: boolean;
}) {
  return (
    <details className="jf-reason">
      <summary
        className={`ax-btn ax-btn--sm ${danger ? "ax-btn--soft-danger" : "ax-btn--secondary"}`}
      >
        {label}
      </summary>
      <ActionForm endpoint={endpoint} back={back} ok={ok} className="jf-reason__form">
        <label className="ax-field__label" htmlFor={`${endpoint.replace(/\W+/g, "-")}${field}`}>
          Motif (obligatoire)
        </label>
        <textarea
          id={`${endpoint.replace(/\W+/g, "-")}${field}`}
          name={field}
          className="ax-textarea"
          rows={2}
          required
          maxLength={300}
          placeholder={placeholder}
        />
        <Submit className={`ax-btn ax-btn--sm ax-btn--primary${danger ? " ax-btn--danger" : ""}`}>
          {confirm}
        </Submit>
      </ActionForm>
    </details>
  );
}

/** Liste « libellé : valeur » des fiches. */
export function Facts({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="jf-facts">
      {items.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v || "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

export function PersonLink({ href, name }: { href: string; name: string }) {
  return (
    <Link href={href} className="jf-link">
      {name}
    </Link>
  );
}
