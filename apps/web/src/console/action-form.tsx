"use client";

/**
 * Formulaire d'action de la console (POST vers une action de l'API, retour sur `back`).
 *
 * Avec JavaScript, l'envoi passe par `submitConsoleAction` : en cas de réussite, retour sur la
 * page avec le message (toast) ; en cas d'erreur, le message s'affiche dans le formulaire et
 * rien ne se recharge (la saisie et la fenêtre modale restent). Sans JavaScript, le formulaire
 * poste vers `consoleAction`, qui revient sur la page avec `?ok=` ou `?erreur=`.
 */
import { createContext, useState, useTransition, type FormEvent, type ReactNode } from "react";

import { consoleAction, submitConsoleAction } from "./actions";

/** Envoi en cours (lu par `Submit`, puisque `useFormStatus` ne voit pas ce type d'envoi). */
export const Sending = createContext(false);

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
  const [error, setError] = useState("");
  const [sending, startTransition] = useTransition();

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (sending) return;
    const data = new FormData(e.currentTarget);
    setError("");
    startTransition(async () => {
      const result = await submitConsoleAction(data);
      if (result?.error) setError(result.error);
    });
  }

  return (
    <form action={consoleAction} className={className} onSubmit={onSubmit} aria-busy={sending}>
      <input type="hidden" name="_endpoint" value={endpoint} />
      <input type="hidden" name="_back" value={back} />
      <input type="hidden" name="_ok" value={ok} />
      {error && (
        <div className="ax-alert ax-alert--danger jf-form-error jf-form__wide" role="alert">
          <i className="bi bi-exclamation-triangle ax-alert__icon" aria-hidden="true" />
          <div className="ax-alert__content">
            <p className="ax-alert__message">{error}</p>
          </div>
        </div>
      )}
      <Sending value={sending}>{children}</Sending>
    </form>
  );
}
