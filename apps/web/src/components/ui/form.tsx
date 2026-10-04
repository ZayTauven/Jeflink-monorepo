// Éléments de formulaire Jeflink : cibles de 48 px au moins, libellé toujours visible, erreur en
// texte (jamais la couleur seule), anneau de focus `accent-strong`.
import type { ReactNode } from "react";

import { AlertIcon } from "./icons";

export const inputClass =
  "min-h-12 w-full rounded-card border border-line-strong bg-surface px-4 py-3 text-base text-ink " +
  "placeholder:text-ink-muted focus-visible:outline-2 focus-visible:outline-offset-2 " +
  "focus-visible:outline-accent-strong aria-invalid:border-danger";

export function fieldIds(id: string) {
  return { hint: `${id}-hint`, error: `${id}-error` };
}

/** `aria-describedby` d'un champ : son aide, puis son erreur si elle existe. */
export function describedBy(id: string, parts: { hint?: boolean; error?: boolean }) {
  const ids = fieldIds(id);
  const out = [parts.hint ? ids.hint : "", parts.error ? ids.error : ""].filter(Boolean);
  return out.length ? out.join(" ") : undefined;
}

export function FieldError({ id, children }: { id: string; children: ReactNode }) {
  return (
    <p id={fieldIds(id).error} className="flex gap-2 text-sm font-medium text-danger">
      <AlertIcon className="mt-0.5 size-4 shrink-0" />
      <span>{children}</span>
    </p>
  );
}

/** Champ à libellé : le contrôle (`children`) porte `id` et `describedBy(id, …)`. */
export function Field({
  id,
  label,
  hint,
  error,
  children,
}: {
  id: string;
  label: string;
  hint?: ReactNode;
  error?: string | undefined;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-base font-medium text-ink">
        {label}
      </label>
      {hint ? (
        <p id={fieldIds(id).hint} className="text-sm leading-relaxed text-ink-muted">
          {hint}
        </p>
      ) : null}
      {children}
      {error ? <FieldError id={id}>{error}</FieldError> : null}
    </div>
  );
}

/** Groupe de choix (radios) : `legend` visible, erreur reliée. */
export function Fieldset({
  id,
  legend,
  hint,
  error,
  children,
}: {
  id: string;
  legend: string;
  hint?: ReactNode;
  error?: string | undefined;
  children: ReactNode;
}) {
  return (
    <fieldset
      aria-describedby={describedBy(id, { hint: Boolean(hint), error: Boolean(error) })}
      className="flex min-w-0 flex-col gap-3"
    >
      <legend className="mb-1 text-base font-medium text-ink">{legend}</legend>
      {hint ? (
        <p id={fieldIds(id).hint} className="text-sm leading-relaxed text-ink-muted">
          {hint}
        </p>
      ) : null}
      {children}
      {error ? <FieldError id={id}>{error}</FieldError> : null}
    </fieldset>
  );
}

/** Choix en ligne de 48 px : radio ou case, le libellé entier est cliquable. */
export function Choice({
  type = "radio",
  name,
  value,
  checked,
  onChange,
  children,
  description,
}: {
  type?: "radio" | "checkbox";
  name?: string;
  value?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  children: ReactNode;
  description?: ReactNode;
}) {
  return (
    <label
      className={`flex min-h-12 cursor-pointer items-start gap-3 rounded-card border bg-surface px-4 py-3 text-base text-ink has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent-strong ${
        checked ? "border-ink" : "border-line-strong"
      }`}
    >
      <input
        type={type}
        name={name}
        value={value}
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-0.5 size-5 shrink-0 accent-accent-strong"
      />
      <span className="flex flex-col gap-1">
        <span className="font-medium">{children}</span>
        {description ? <span className="text-sm text-ink-muted">{description}</span> : null}
      </span>
    </label>
  );
}
