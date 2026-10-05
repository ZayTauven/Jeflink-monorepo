"use client";

// Étape 1 : le numéro (spec 001, « Client, première connexion »). Question : « À quel numéro
// envoyer le code ? ». Action principale : « Recevoir le code ».
import type { Region } from "@jeflink/api-client";
import { useTranslations } from "next-intl";
import { type FormEvent, useId, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button, ButtonLink } from "@/components/ui/button";
import type { LoginError } from "@/lib/login/errors";
import { formatPhoneInput, isPlausiblePhone } from "@/lib/login/phone";

import { StepHeader } from "./step-header";
import { LoginErrorAlert } from "./support";

const INCOMPLETE: LoginError = {
  code: "phone_invalid",
  key: "phone_invalid",
  support: false,
  restart: false,
  region: false,
};

type Props = {
  regions: Region[];
  dialCode: string;
  onDialCode: (dialCode: string) => void;
  phone: string;
  onPhone: (phone: string) => void;
  onSubmit: () => void;
  pending: boolean;
  error: LoginError | null;
  /** Lien de nouvel essai de refresh (`raison=indisponible`), sinon null. */
  retryHref: string | null;
  focusHeading: boolean;
};

export function PhoneStep(props: Props) {
  const t = useTranslations("connexion.phone");
  const inputId = useId();
  const errorId = useId();
  const [incomplete, setIncomplete] = useState(false);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (props.pending) return;
    // Bouton toujours actif : un numéro incomplet s'explique au lieu d'un bouton grisé.
    const plausible = isPlausiblePhone(props.phone);
    setIncomplete(!plausible);
    if (plausible) props.onSubmit();
  };
  const error = incomplete ? INCOMPLETE : props.error;

  return (
    <div className="flex flex-col gap-8">
      {props.retryHref ? (
        <Alert
          tone="info"
          action={
            <ButtonLink href={props.retryHref} variant="secondary" className="self-start">
              {t("retry")}
            </ButtonLink>
          }
        >
          {t("unavailable")}
        </Alert>
      ) : null}

      <StepHeader title={t("title")} focus={props.focusHeading}>
        <p>{t("lead")}</p>
      </StepHeader>

      <form onSubmit={submit} className="flex flex-col gap-6" noValidate>
        <div className="flex flex-col gap-2">
          <label htmlFor={inputId} className="text-sm font-medium text-ink">
            {t("label")}
            <span className="sr-only"> ({props.dialCode})</span>
          </label>
          <div className="flex min-h-14 items-stretch overflow-hidden rounded-card border border-line-strong bg-surface focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent-strong">
            {props.regions.length > 1 ? (
              <select
                aria-label={t("country")}
                value={props.dialCode}
                onChange={(event) => props.onDialCode(event.target.value)}
                className="border-r border-line bg-sand px-3 text-base text-ink outline-none"
              >
                {props.regions.map((region) => (
                  <option key={region.region} value={region.dial_code}>
                    {region.label} {region.dial_code}
                  </option>
                ))}
              </select>
            ) : (
              <span
                aria-hidden="true"
                className="flex items-center border-r border-line bg-sand px-4 text-base font-medium text-ink"
              >
                {props.dialCode}
              </span>
            )}
            <input
              id={inputId}
              type="tel"
              inputMode="tel"
              autoComplete="tel-national"
              placeholder={t("placeholder")}
              value={props.phone}
              onChange={(event) => {
                setIncomplete(false);
                props.onPhone(formatPhoneInput(event.target.value));
              }}
              aria-invalid={error?.code === "phone_invalid" || undefined}
              aria-describedby={error ? errorId : undefined}
              className="min-w-0 flex-1 bg-transparent px-4 text-lg tracking-wide text-ink outline-none placeholder:text-ink-muted"
            />
          </div>
        </div>

        {error ? <LoginErrorAlert error={error} id={errorId} /> : null}

        <Button type="submit" disabled={props.pending} aria-busy={props.pending} className="w-full">
          {props.pending ? t("sending") : t("submit")}
        </Button>

        <p className="text-sm leading-relaxed text-ink-muted">
          {t.rich("terms", {
            terms: (chunks) => (
              <a href="/conditions" className="text-accent-strong underline underline-offset-4">
                {chunks}
              </a>
            ),
            privacy: (chunks) => (
              <a
                href="/confidentialite"
                className="text-accent-strong underline underline-offset-4"
              >
                {chunks}
              </a>
            ),
          })}
        </p>
      </form>
    </div>
  );
}
