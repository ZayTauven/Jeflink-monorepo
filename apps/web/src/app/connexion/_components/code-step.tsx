"use client";

// Étape 2 : le code reçu par SMS (spec 001, « Code » ; T1). Question : « Quel code avez-vous
// reçu ? ». Action principale : « Valider ». Pas de compte à rebours ; le champ reste toujours
// actif et garde sa saisie, qu'il s'agisse d'une coupure réseau ou d'un code faux.
import { useTranslations } from "next-intl";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ArrowLeftIcon, ClockIcon, PhoneIcon, SignalIcon } from "@/components/ui/icons";
import type { StoredChallenge } from "@/lib/login/challenge-store";
import type { LoginError } from "@/lib/login/errors";

import { StepHeader } from "./step-header";
import { LoginErrorAlert, SupportLink } from "./support";

type Props = {
  challenge: StoredChallenge;
  onVerify: (code: string) => void;
  onResend: () => void;
  onChangePhone: () => void;
  verifying: boolean;
  resending: boolean;
  resent: boolean;
  error: LoginError | null;
};

type OtpCredential = Credential & { code?: string };

export function CodeStep(props: Props) {
  const t = useTranslations("connexion.code");
  const inputId = useId();
  const hintId = useId();
  const errorId = useId();
  const [code, setCode] = useState("");
  const length = props.challenge.code_length;
  const [canResend, setCanResend] = useState(false);
  const submitted = useRef<string | null>(null);
  const { onVerify, verifying, error } = props;

  // « Renvoyer » n'apparaît qu'à partir de resend_available_at (60 s), sans compte à rebours.
  useEffect(() => {
    const wait = Date.parse(props.challenge.resend_available_at) - Date.now();
    const remaining = props.challenge.deliveries_remaining > 0;
    setCanResend(remaining && wait <= 0);
    if (!remaining || wait <= 0) return;
    const timer = window.setTimeout(() => setCanResend(true), wait);
    return () => window.clearTimeout(timer);
  }, [props.challenge.resend_available_at, props.challenge.deliveries_remaining]);

  // WebOTP : le code du SMS (dernière ligne `@jeflink.sn #123456`) se remplit tout seul.
  useEffect(() => {
    if (!("OTPCredential" in window)) return;
    const abort = new AbortController();
    navigator.credentials
      .get({ otp: { transport: ["sms"] }, signal: abort.signal } as CredentialRequestOptions)
      .then((credential) => {
        const received = (credential as OtpCredential | null)?.code ?? "";
        if (/^\d+$/.test(received)) setCode(received.slice(0, length));
      })
      .catch(() => undefined); // refus, délai ou abandon : saisie manuelle
    return () => abort.abort();
  }, [length]);

  // Code complet : validation sans appui (une seule fois par code saisi).
  useEffect(() => {
    if (code.length === length && !verifying && submitted.current !== code) {
      submitted.current = code;
      onVerify(code);
    }
  }, [code, length, verifying, onVerify]);

  // Coupure réseau : on réessaie de nous-mêmes au retour du réseau, la saisie est gardée.
  useEffect(() => {
    if (error?.code !== "network") return;
    const retry = () => {
      if (code.length === length) onVerify(code);
    };
    window.addEventListener("online", retry);
    return () => window.removeEventListener("online", retry);
  }, [error, code, length, onVerify]);

  const input = useRef<HTMLInputElement>(null);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (code.length !== length) input.current?.focus();
    else if (!verifying) {
      submitted.current = code;
      onVerify(code);
    }
  };

  return (
    <div className="flex flex-col gap-8">
      <StepHeader title={t("title")}>
        <p>{t("sentTo", { phone: props.challenge.phone_display })}</p>
        <button
          type="button"
          onClick={props.onChangePhone}
          className="mt-2 inline-flex min-h-12 items-center gap-2 font-medium text-accent-strong underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-strong"
        >
          <ArrowLeftIcon className="size-4" />
          {t("change")}
        </button>
      </StepHeader>

      <form onSubmit={submit} className="flex flex-col gap-6" noValidate>
        <div className="flex flex-col gap-2">
          <label htmlFor={inputId} className="text-sm font-medium text-ink">
            {t("label", { length })}
          </label>
          <input
            ref={input}
            id={inputId}
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]*"
            maxLength={length}
            value={code}
            onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, length))}
            aria-invalid={error?.code === "otp_invalid" || undefined}
            aria-describedby={error ? `${hintId} ${errorId}` : hintId}
            className="min-h-16 w-full rounded-card border border-line-strong bg-surface px-4 text-center indent-[0.3em] font-display text-3xl tracking-[0.3em] text-ink outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-strong"
          />
          <div id={hintId} className="flex flex-col gap-1 text-sm text-ink-muted">
            <p>{t("delay")}</p>
            <p>{t("warning")}</p>
          </div>
        </div>

        {error ? <LoginErrorAlert error={error} id={errorId} /> : null}
        {props.resent && !error ? <Alert tone="success">{t("resent")}</Alert> : null}

        <Button type="submit" disabled={verifying} aria-busy={verifying} className="w-full">
          {verifying ? t("checking") : t("submit")}
        </Button>

        {canResend ? (
          <Button
            variant="secondary"
            onClick={props.onResend}
            disabled={props.resending}
            aria-busy={props.resending}
            className="w-full"
          >
            {props.resending ? t("resending") : t("resend")}
          </Button>
        ) : null}
      </form>

      <details className="group rounded-card border border-line bg-surface">
        <summary className="flex min-h-12 cursor-pointer list-none items-center [&::-webkit-details-marker]:hidden justify-between gap-3 px-4 font-medium text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-strong">
          {t("helpToggle")}
          <span
            aria-hidden="true"
            className="text-xl text-ink-muted transition-transform group-open:rotate-45"
          >
            +
          </span>
        </summary>
        <div className="flex flex-col gap-5 border-t border-line px-4 py-5">
          <ul className="flex flex-col gap-4">
            {(
              [
                [PhoneIcon, t("helpNumber")],
                [SignalIcon, t("helpNetwork")],
                [ClockIcon, t("helpWait")],
              ] as const
            ).map(([Icon, text]) => (
              <li key={text} className="flex items-center gap-4">
                <span className="flex size-12 shrink-0 items-center justify-center rounded-pill bg-sand text-ink">
                  <Icon className="size-6" />
                </span>
                <span className="text-base text-ink">{text}</span>
              </li>
            ))}
          </ul>
          <SupportLink />
        </div>
      </details>
    </div>
  );
}
