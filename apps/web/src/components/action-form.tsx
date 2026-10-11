"use client";

import { useRef, useState, type FormEvent, type ReactNode } from "react";

type Result =
  { ok: true; redirect: string } | { ok: false; error: string; fields?: Record<string, string> };

/**
 * Formulaire posté vers un route handler de src/app/act. Avec JavaScript : envoi en fetch,
 * erreurs affichées sans perdre la saisie, puis chargement complet de la page suivante.
 * Sans JavaScript : envoi classique, le serveur redirige.
 *
 * Ne jamais donner la classe `submit` au bouton : main.js de Crafto l'intercepte.
 */
export function ActionForm({
  action,
  labels = {},
  className,
  children,
}: {
  action: string;
  labels?: Record<string, string>;
  className?: string;
  children: ReactNode;
}) {
  const formRef = useRef<HTMLFormElement>(null);
  const [pending, setPending] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    form.querySelectorAll(".is-invalid").forEach((el) => el.classList.remove("is-invalid"));
    setPending(true);
    setErrors([]);
    let result: Result;
    try {
      const res = await fetch(action, {
        method: "POST",
        body: new FormData(form),
        headers: { "x-jeflink-fetch": "1" },
      });
      result = (await res.json()) as Result;
    } catch {
      result = { ok: false, error: "Connexion impossible. Vérifiez votre réseau et réessayez." };
    }
    if (result.ok) {
      window.location.assign(result.redirect);
      return;
    }
    const fields = result.fields ?? {};
    for (const name of Object.keys(fields)) {
      form.querySelectorAll(`[name="${name}"]`).forEach((el) => el.classList.add("is-invalid"));
    }
    setErrors([
      ...(result.error ? [result.error] : []),
      ...Object.entries(fields).map(([k, v]) => (labels[k] ? `${labels[k]} : ${v}` : v)),
    ]);
    setPending(false);
    formRef.current?.querySelector<HTMLElement>(".alert")?.focus();
  }

  return (
    <form ref={formRef} action={action} method="post" onSubmit={onSubmit} className={className}>
      {errors.length > 0 && (
        <div className="alert alert-danger mb-25px" role="alert" tabIndex={-1}>
          {errors.map((e) => (
            <div key={e}>{e}</div>
          ))}
        </div>
      )}
      <fieldset disabled={pending} aria-busy={pending} className="border-0 p-0 m-0">
        {children}
      </fieldset>
    </form>
  );
}
