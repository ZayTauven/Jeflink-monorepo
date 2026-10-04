"use client";

// « Le pro n'est pas venu » (spec 004, web 1). Question métier : « Le pro est en retard : que
// faire avant de renoncer à lui ? ». Proposé seulement quand l'API le permet (`can_report_no_show` :
// après le créneau et une marge). L'écran propose d'abord d'appeler le pro, puis de le signaler.
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button, ButtonLink } from "@/components/ui/button";
import { PhoneIcon } from "@/components/ui/icons";

import { noShowAction } from "../booking-actions";
import { ActionError } from "./action-error";
import { useBookingAction } from "./use-booking-action";

export function NoShowPanel({
  bookingId,
  requestId,
  providerName,
  phone,
  supportHref,
}: {
  bookingId: string;
  requestId: string;
  providerName: string;
  /** Numéro E.164 du pro, ou null. */
  phone: string | null;
  supportHref: string | null;
}) {
  const t = useTranslations("bookings.noShow");
  const router = useRouter();
  const action = useBookingAction();
  const [confirming, setConfirming] = useState(false);

  async function confirm() {
    if (await action.run(() => noShowAction(bookingId))) {
      // La demande est rouverte : la page de la demande l'explique (`?signale=absence`).
      router.replace(`/compte/demandes/${requestId}?signale=absence`);
    }
  }

  return (
    <section
      aria-labelledby="noshow-title"
      className="flex flex-col gap-4 rounded-card border border-line bg-surface p-5 sm:p-6"
    >
      <h2 id="noshow-title" className="font-display text-2xl tracking-tight">
        {t("title")}
      </h2>
      <p className="text-base leading-relaxed text-ink">{t("lead")}</p>

      {phone ? (
        <ButtonLink href={`tel:${phone}`} variant="primary" className="self-start">
          <PhoneIcon className="size-5" />
          {t("call", { name: providerName })}
        </ButtonLink>
      ) : null}

      {action.error ? <ActionError error={action.error} supportHref={supportHref} /> : null}

      {confirming ? (
        <div className="flex flex-col gap-3 rounded-card border border-line-strong p-4">
          <p className="text-base font-medium text-ink">{t("confirmTitle")}</p>
          <p className="text-base text-ink-muted">{t("confirmLead")}</p>
          <div className="flex flex-col gap-3 sm:flex-row">
            <Button onClick={confirm} disabled={action.pending} aria-busy={action.pending}>
              {action.pending ? t("sending") : t("confirmYes")}
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
        <Button variant="secondary" className="self-start" onClick={() => setConfirming(true)}>
          {t("report")}
        </Button>
      )}
    </section>
  );
}
