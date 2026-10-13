/**
 * Briques des rubriques de la console (Server Components) : message de retour, onglets,
 * pagination, avatars, étoiles et formulaires d'action branchés sur `consoleAction`.
 */
import Link from "next/link";
import type { ReactNode } from "react";

import { ActionForm } from "./action-form";
import { qs, type Query } from "./data";
import { CloseModal, Modal } from "./modal";
import { LinkPending } from "./pending";
import { Submit } from "./submit";

/**
 * Message après une action (?ok= / ?erreur=). Avec JavaScript, c'est un toast (`Toaster`,
 * monté par la coque) ; sans JavaScript, cette alerte en haut de la page.
 */
export function Flash({ ok, erreur }: { ok?: string; erreur?: string }) {
  if (!ok && !erreur) return null;
  return (
    <noscript>
      <div
        className={`ax-alert ${erreur ? "ax-alert--danger" : "ax-alert--success"} mb-6`}
        role={erreur ? "alert" : "status"}
      >
        <i
          className={`bi ${erreur ? "bi-exclamation-triangle" : "bi-check2-circle"} ax-alert__icon`}
          aria-hidden="true"
        />
        <div className="ax-alert__content">
          <p className="ax-alert__message">{erreur || ok}</p>
        </div>
      </div>
    </noscript>
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
              <LinkPending />
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

/**
 * Un filtre de liste : paramètre de l'adresse, libellé, valeur lisible. `flag` : case à cocher,
 * la puce n'affiche que le libellé. Valeur introuvable (métier retiré…) : la valeur brute.
 */
export type FilterChip = { name: string; label: string; value?: string; flag?: boolean };

/** Adresse de la liste sans ces filtres (ni la page) ; l'onglet reste. */
export function withoutFilters(base: string, params: Query, names: string[]): string {
  return `${base}${qs(params, Object.fromEntries([...names, "page"].map((n) => [n, undefined])))}`;
}

/** Filtres actifs, chacun en puce qui le retire, et « Tout effacer ». */
export function ActiveFilters({
  base,
  params,
  filters,
}: {
  base: string;
  params: Query;
  filters: FilterChip[];
}) {
  const active = filters.filter((f) => params[f.name]);
  if (active.length === 0) return null;
  return (
    <div className="jf-chips-bar" aria-label="Filtres actifs" role="group">
      {active.map((f) => {
        const text = f.flag ? f.label : `${f.label} : ${f.value || params[f.name]}`;
        return (
          <Link
            key={f.name}
            href={withoutFilters(base, params, [f.name])}
            className="ax-badge ax-badge--soft ax-badge--accent ax-badge--chip jf-chip"
            aria-label={`Retirer le filtre ${text}`}
            scroll={false}
          >
            {text}
            <i className="bi bi-x-lg" aria-hidden="true" />
            <LinkPending />
          </Link>
        );
      })}
      {active.length > 1 && (
        <Link
          href={withoutFilters(
            base,
            params,
            active.map((f) => f.name),
          )}
          className="jf-link jf-chips-bar__clear"
          scroll={false}
        >
          Tout effacer
          <LinkPending />
        </Link>
      )}
    </div>
  );
}

/**
 * « Trier par » d'une liste (paramètre `tri`, transmis à l'API en `sort`). La première
 * option, vide, est le tri par défaut ; le tri n'est pas un filtre (pas de puce).
 */
export function SortField({ value, options }: { value?: string; options: [string, string][] }) {
  return (
    <div className="ax-field">
      <label className="ax-field__label" htmlFor="tri">
        Trier par
      </label>
      <select id="tri" name="tri" className="ax-select" defaultValue={value ?? ""}>
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </div>
  );
}

export { ActionForm };

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
              <LinkPending />
            </Link>
          ) : (
            <span className="ax-pagination__prev" aria-hidden="true">
              <i className="bi bi-chevron-left" />
            </span>
          )}
          {page < pages ? (
            <Link className="ax-pagination__next" href={at(page + 1)} aria-label="Page suivante">
              <i className="bi bi-chevron-right" aria-hidden="true" />
              <LinkPending />
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
 * Action qui demande un motif (suspendre, refuser, masquer, annuler) : une fenêtre de
 * confirmation s'ouvre, le motif est obligatoire et sert de confirmation. `subject` rappelle
 * sur quoi porte l'action (nom du pro, auteur de l'avis…).
 */
export function ReasonAction({
  endpoint,
  back,
  ok,
  label,
  confirm,
  title,
  subject,
  field = "reason",
  fieldLabel = "Motif (obligatoire)",
  maxLength = 300,
  hint = "Il reste dans le journal de la console.",
  placeholder,
  danger = true,
}: {
  endpoint: string;
  back: string;
  ok: string;
  label: string;
  confirm: string;
  /** Titre de la fenêtre ; par défaut le libellé du bouton. */
  title?: string;
  subject?: ReactNode;
  field?: string;
  fieldLabel?: string;
  maxLength?: number;
  hint?: string;
  placeholder: string;
  danger?: boolean;
}) {
  const id = `${endpoint.replace(/\W+/g, "-")}${field}`;
  return (
    <Modal
      trigger={label}
      triggerClassName={`ax-btn ax-btn--sm ${danger ? "ax-btn--soft-danger" : "ax-btn--secondary"}`}
      title={title ?? label.replace(/…$/, "")}
      subtitle={subject}
      icon={danger ? "bi-exclamation-triangle" : "bi-info-circle"}
      danger={danger}
      size="sm"
      closeOnBackdrop
    >
      <ActionForm endpoint={endpoint} back={back} ok={ok} className="jf-dialog__form">
        <div className="ax-field">
          <label className="ax-field__label" htmlFor={id}>
            {fieldLabel}
          </label>
          <textarea
            id={id}
            name={field}
            className="ax-textarea"
            rows={3}
            required
            maxLength={maxLength}
            placeholder={placeholder}
            aria-describedby={`${id}-aide`}
          />
          <p className="ax-field__hint" id={`${id}-aide`}>
            {hint}
          </p>
        </div>
        <div className="jf-dialog__actions">
          <CloseModal />
          <Submit className={`ax-btn ax-btn--sm ax-btn--primary${danger ? " ax-btn--danger" : ""}`}>
            {confirm}
          </Submit>
        </div>
      </ActionForm>
    </Modal>
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
