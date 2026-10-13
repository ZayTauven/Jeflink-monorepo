/** Briques de page de la console (Server Components), sur les classes vireo. */
import Link from "next/link";
import type { ReactNode } from "react";

import type { RequestStatus } from "@/lib/types";

import { LinkPending } from "./pending";

export function PageHead({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="ax-page-head">
      <div className="ax-page-head__row">
        <div>
          <h1 className="ax-page-head__title">{title}</h1>
          {subtitle && <p className="ax-page-head__subtitle">{subtitle}</p>}
        </div>
        {actions && <div className="ax-page-head__actions">{actions}</div>}
      </div>
    </div>
  );
}

export function Card({
  title,
  eyebrow,
  subtitle,
  actions,
  className = "",
  children,
}: {
  title: string;
  eyebrow?: string;
  subtitle?: string;
  actions?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={`ax-card ${className}`} aria-label={title}>
      <div className="ax-card__header">
        <div className="ax-card__titles">
          {eyebrow && <span className="ax-card__eyebrow">{eyebrow}</span>}
          <h2 className="ax-card__title">{title}</h2>
          {subtitle && <p className="ax-card__subtitle">{subtitle}</p>}
        </div>
        {actions && <div className="ax-card__actions">{actions}</div>}
      </div>
      <div className="ax-card__body" style={{ paddingTop: 0 }}>
        {children}
      </div>
    </section>
  );
}

/** Variation par rapport à la période précédente. `better` : sens souhaitable. */
export function Delta({
  now,
  before,
  better = "up",
  unit = "%",
}: {
  now: number | null;
  before: number | null;
  better?: "up" | "down";
  unit?: "%" | "pts";
}) {
  if (now === null || before === null || before === 0) {
    return <span className="ax-kpi__delta">nouveau</span>;
  }
  const diff = unit === "pts" ? now - before : Math.round(((now - before) / before) * 100);
  if (diff === 0) return <span className="ax-kpi__delta">stable</span>;
  const up = diff > 0;
  const good = up === (better === "up");
  const sign = up ? "+" : "−";
  const value = `${sign}${Math.abs(diff).toLocaleString("fr-FR")}${unit === "pts" ? " pts" : " %"}`;
  return (
    <span
      className={`ax-kpi__delta ${good ? "ax-kpi__delta--up" : "ax-kpi__delta--down"}`}
      title="Par rapport à la période précédente"
    >
      <i className={`bi ${up ? "bi-arrow-up-short" : "bi-arrow-down-short"}`} aria-hidden="true" />
      {value}
    </span>
  );
}

/** Anneau de progression (pourcentage), à la place de l'icône d'un indicateur. */
function Ring({ percent }: { percent: number }) {
  const r = 18;
  const length = 2 * Math.PI * r;
  const p = Math.min(100, Math.max(0, percent));
  return (
    <span className="ax-progress ax-progress--circle jf-ring" aria-hidden="true">
      <svg width="44" height="44" viewBox="0 0 44 44">
        <circle className="ax-progress__ring-track" cx="22" cy="22" r={r} strokeWidth="4" />
        <circle
          className="ax-progress__ring-fill"
          cx="22"
          cy="22"
          r={r}
          strokeWidth="4"
          strokeDasharray={length}
          strokeDashoffset={length * (1 - p / 100)}
          transform="rotate(-90 22 22)"
        />
      </svg>
    </span>
  );
}

/** Jauge fine (utilisations d'un code promo…), le chiffre exact est affiché à côté. */
export function Meter({ value, max }: { value: number; max: number }) {
  const p = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div
      className={`ax-progress ax-progress--xs jf-meter${p >= 90 ? " ax-progress--warning" : ""}`}
      aria-hidden="true"
    >
      <div className="ax-progress__track">
        <div className="ax-progress__fill" style={{ width: `${p}%` }} />
      </div>
    </div>
  );
}

export function Kpi({
  label,
  value,
  unit,
  icon,
  ring,
  delta,
  foot,
  dark = false,
  className = "ax-col--3",
}: {
  label: string;
  value: string;
  unit?: string;
  icon: string;
  /** Pourcentage : affiché en anneau à la place de l'icône. */
  ring?: number | null;
  delta?: ReactNode;
  foot?: ReactNode;
  dark?: boolean;
  className?: string;
}) {
  return (
    <div className={`ax-card ax-kpi ${className}`} role="group" aria-label={label}>
      <div className="ax-card__body">
        <div className="ax-kpi__top">
          {ring !== undefined && ring !== null ? (
            <Ring percent={ring} />
          ) : (
            <span className={`jf-kpi-icon${dark ? " jf-kpi-icon--dark" : ""}`} aria-hidden="true">
              <i className={`bi ${icon}`} />
            </span>
          )}
          {delta}
        </div>
        <div className="ax-kpi__label">{label}</div>
        <div className="ax-kpi__value ax-num">
          {value}
          {unit && <small className="jf-kpi-unit">{unit}</small>}
        </div>
        {foot && (
          <div className="ax-kpi__caption" style={{ gridColumn: "1 / -1", gridRow: 4 }}>
            {foot}
          </div>
        )}
      </div>
    </div>
  );
}

const STATUS_CLASS: Record<RequestStatus, string> = {
  open: "jf-status--open",
  booked: "jf-status--booked",
  done: "jf-status--done",
  cancelled: "jf-status--cancelled",
};

export function Status({ status, label }: { status: RequestStatus; label: string }) {
  return <span className={`jf-status ${STATUS_CLASS[status]}`}>{label}</span>;
}

/** Sélecteur de période (liens, fonctionne sans JavaScript). */
export function PeriodSwitch({ days, base }: { days: number; base: string }) {
  return (
    <div
      className="ax-btn-group ax-btn-group--segmented jf-segmented"
      role="group"
      aria-label="Période"
    >
      {[7, 30, 90].map((d) => (
        <Link
          key={d}
          href={`${base}?jours=${d}`}
          className={`ax-btn ax-btn--sm${d === days ? " is-selected" : ""}`}
          aria-current={d === days ? "true" : undefined}
        >
          {d} jours
          <LinkPending />
        </Link>
      ))}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p style={{ color: "var(--ax-text-muted)", margin: 0 }}>{children}</p>;
}
