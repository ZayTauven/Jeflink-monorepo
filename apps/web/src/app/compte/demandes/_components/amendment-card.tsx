"use client";

// Avenant proposé par le pro (spec 004, web 2). Question métier : « Le prix change sur place :
// est-ce que j'accepte ? ». Aucun prix ne change sans un geste du client. Une hausse au-delà du
// seuil de l'API (`requires_confirmation`) demande une confirmation dans la page, jamais
// `window.confirm` ; une baisse n'en demande aucune. Refuser garde le prix courant.
import type { Amendment } from "@jeflink/api-client";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { AlertIcon } from "@/components/ui/icons";
import { changePercent, direction, needsConfirmation } from "@/lib/bookings/amendments";
import { formatXof } from "@/lib/requests/format";
import { readableLabel } from "@/lib/requests/quotes";

import { amendmentAction } from "../booking-actions";
import { ActionError } from "./action-error";
import { useBookingAction } from "./use-booking-action";

export function AmendmentCard({
  bookingId,
  amendment,
  supportHref,
}: {
  bookingId: string;
  amendment: Amendment;
  supportHref: string | null;
}) {
  const t = useTranslations("bookings.amendment");
  const tLine = useTranslations("requests.quote.line");
  const action = useBookingAction();
  const [confirming, setConfirming] = useState(false);
  const [which, setWhich] = useState<"accept" | "decline" | null>(null);
  const way = direction(amendment);
  const percent = changePercent(amendment);
  const confirmFirst = needsConfirmation(amendment);

  // L'API demande la confirmation que la page n'avait pas jugée utile : on l'affiche, sans erreur.
  const needsStep = action.error?.code === "amendment_confirmation_required";
  useEffect(() => {
    if (needsStep) {
      setConfirming(true);
      action.clearError();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [needsStep]);

  function decide(decision: "accept" | "decline", confirm = false) {
    setWhich(decision);
    return action.run(() =>
      amendmentAction({
        bookingId,
        amendmentId: amendment.public_id,
        decision,
        total: amendment.total_xof,
        confirm,
      }),
    );
  }

  return (
    <section
      aria-labelledby="amendment-title"
      className="flex flex-col gap-5 rounded-card border-2 border-ink bg-surface p-5 sm:p-6"
    >
      <h2 id="amendment-title" className="font-display text-2xl tracking-tight">
        {t("title")}
      </h2>
      <p className="text-base leading-relaxed text-ink">
        {t(`reason.${amendment.reason}`)}
        {amendment.note.trim() ? ` : ${amendment.note.trim()}` : ""}
      </p>

      <div className="flex flex-col gap-1">
        <p className="text-sm text-ink-muted">{t("newPrice")}</p>
        <p className="font-display text-5xl font-semibold tracking-tight text-ink">
          {formatXof(amendment.total_xof)}
        </p>
        <p className="text-base text-ink-muted">
          {t("was", { amount: formatXof(amendment.previous_amount_xof) })}
          {way === "same" ? "" : ` · ${t(way === "up" ? "up" : "down", { percent })}`}
        </p>
      </div>

      {amendment.lines.length > 0 ? (
        <ul className="flex flex-col gap-2 rounded-card border border-line px-4 py-3">
          {amendment.lines.map((line, index) => (
            <li key={index} className="flex justify-between gap-4 text-base text-ink">
              <span>{readableLabel(line.label) || tLine(line.kind)}</span>
              <span className="whitespace-nowrap">{formatXof(line.amount_xof)}</span>
            </li>
          ))}
        </ul>
      ) : null}

      <p className="rounded-card bg-sand p-4 text-base font-medium leading-relaxed text-ink">
        {t("payment")}
      </p>

      {action.error && !needsStep ? (
        <ActionError error={action.error} supportHref={supportHref} />
      ) : null}

      {confirmFirst && !confirming ? (
        <Alert tone="info">{t("bigIncrease", { percent })}</Alert>
      ) : null}
      {confirming ? (
        <div className="flex flex-col gap-3 rounded-card border border-line-strong p-4">
          <p className="flex gap-2 text-base font-medium text-ink">
            <AlertIcon className="mt-0.5 size-5 shrink-0 text-warning" />
            <span>
              {t("confirmTitle", {
                percent,
                amount: formatXof(amendment.total_xof),
                was: formatXof(amendment.previous_amount_xof),
              })}
            </span>
          </p>
          <div className="flex flex-col gap-3 sm:flex-row">
            <Button
              onClick={() => decide("accept", true)}
              disabled={action.pending}
              aria-busy={action.pending}
            >
              {action.pending && which === "accept" ? t("accepting") : t("confirmYes")}
            </Button>
            <Button
              variant="secondary"
              onClick={() => setConfirming(false)}
              disabled={action.pending}
            >
              {t("confirmNo")}
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3 sm:flex-row">
          <Button
            onClick={() => (confirmFirst ? setConfirming(true) : decide("accept"))}
            disabled={action.pending}
            aria-busy={action.pending}
          >
            {action.pending && which === "accept"
              ? t("accepting")
              : t("accept", { amount: formatXof(amendment.total_xof) })}
          </Button>
          <Button variant="secondary" onClick={() => decide("decline")} disabled={action.pending}>
            {action.pending && which === "decline"
              ? t("declining")
              : t("decline", { amount: formatXof(amendment.previous_amount_xof) })}
          </Button>
        </div>
      )}
    </section>
  );
}
