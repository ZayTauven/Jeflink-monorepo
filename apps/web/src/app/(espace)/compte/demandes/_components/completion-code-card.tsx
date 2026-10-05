"use client";

// Code de fin de mission (spec 004, web 1). Question métier : « Quel code donner au pro, et à quel
// moment ? ». Le client le lit ici dès `scheduled` (la page chargée le matin reste lisible hors
// ligne), le reçoit par SMS au départ du pro, et peut le transmettre à un proche (diaspora : le
// lien WhatsApp est construit dans le navigateur). Le code ne va jamais dans un journal ni une URL
// de notre côté ; seul le lien de partage, voulu par le client, le contient.
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button, ButtonLink } from "@/components/ui/button";
import { ChatIcon, InfoIcon } from "@/components/ui/icons";

import { regenerateCodeAction, sendCodeSmsAction } from "../booking-actions";
import { ActionError } from "./action-error";
import { useBookingAction } from "./use-booking-action";

const SHARE_BASE = "https://wa.me/?text=";

export function CompletionCodeCard({
  bookingId,
  code,
  locked,
  canRegenerate,
  canSendSms,
  supportHref,
}: {
  bookingId: string;
  code: string | null;
  locked: boolean;
  canRegenerate: boolean;
  canSendSms: boolean;
  supportHref: string | null;
}) {
  const t = useTranslations("bookings.code");
  const tProblem = useTranslations("bookings.problem");
  const sms = useBookingAction();
  const regen = useBookingAction();
  const [smsSent, setSmsSent] = useState(false);
  const [confirming, setConfirming] = useState(false);

  async function sendSms() {
    if (await sms.run(() => sendCodeSmsAction(bookingId))) setSmsSent(true);
  }

  async function regenerate() {
    if (await regen.run(() => regenerateCodeAction(bookingId))) {
      setConfirming(false);
      setSmsSent(false);
    }
  }

  const showCode = Boolean(code) && !locked;
  if (!showCode && !locked) return null;
  const spaced = code ? code.split("").join(" ") : "";
  const shareHref = code ? `${SHARE_BASE}${encodeURIComponent(t("shareMessage", { code }))}` : null;

  return (
    <section
      aria-labelledby="code-title"
      className="flex flex-col gap-4 rounded-card border border-line bg-surface p-5 sm:p-6"
    >
      <h2 id="code-title" className="font-display text-2xl tracking-tight">
        {t("title")}
      </h2>

      {showCode ? (
        <p className="rounded-card bg-sand py-5 text-center font-display text-5xl font-semibold sm:text-6xl tabular-nums tracking-[0.25em] text-ink">
          <span className="sr-only">{t("codeLabel", { code: spaced })}</span>
          <span aria-hidden="true">{code}</span>
        </p>
      ) : (
        <Alert tone="error">{t("lockedLead")}</Alert>
      )}

      <p className="flex gap-2 text-base font-medium leading-relaxed text-ink">
        <InfoIcon className="mt-0.5 size-5 shrink-0 text-info" />
        <span>{t("warning")}</span>
      </p>

      {showCode ? <p className="text-base text-ink-muted">{t("whenToGive")}</p> : null}

      {smsSent ? <Alert tone="success">{t("smsSent")}</Alert> : null}
      {sms.error ? <ActionError error={sms.error} supportHref={supportHref} /> : null}
      {regen.error ? <ActionError error={regen.error} supportHref={supportHref} /> : null}

      {confirming ? (
        <div className="flex flex-col gap-3 rounded-card border border-line-strong p-4">
          <p className="text-base font-medium text-ink">{t("regenerateTitle")}</p>
          <p className="text-base text-ink-muted">{t("regenerateLead")}</p>
          <div className="flex flex-col gap-3 sm:flex-row">
            <Button onClick={regenerate} disabled={regen.pending} aria-busy={regen.pending}>
              {regen.pending ? t("regenerating") : t("regenerateYes")}
            </Button>
            <Button
              variant="secondary"
              onClick={() => setConfirming(false)}
              disabled={regen.pending}
            >
              {t("regenerateNo")}
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap">
          {locked && canRegenerate ? (
            <Button onClick={() => setConfirming(true)}>{t("regenerateLocked")}</Button>
          ) : null}
          {showCode && canSendSms ? (
            <Button
              variant="secondary"
              onClick={sendSms}
              disabled={sms.pending}
              aria-busy={sms.pending}
            >
              {sms.pending ? t("smsSending") : t("sms")}
            </Button>
          ) : null}
          {shareHref && showCode ? (
            <ButtonLink href={shareHref} target="_blank" rel="noopener noreferrer">
              <ChatIcon className="size-5" />
              {t("share")}
            </ButtonLink>
          ) : null}
          {showCode && canRegenerate ? (
            <Button variant="quiet" onClick={() => setConfirming(true)}>
              {t("regenerate")}
            </Button>
          ) : null}
        </div>
      )}

      {showCode ? <p className="text-sm text-ink-muted">{t("shareNote")}</p> : null}
      {locked && !canRegenerate && !supportHref ? (
        <p className="text-base text-ink-muted">{tProblem("noSupport")}</p>
      ) : null}
      {locked && !canRegenerate && supportHref ? (
        <ButtonLink href={supportHref} target="_blank" rel="noopener noreferrer" variant="primary">
          <ChatIcon className="size-5" />
          {t("lockedSupport")}
        </ButtonLink>
      ) : null}
    </section>
  );
}
