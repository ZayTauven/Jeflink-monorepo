// État du litige (spec 004, web 3) : « Jeflink examine et décide. Pas de remboursement pour
// l'instant. » Rendu serveur. Le texte du client n'est jamais renvoyé par l'API.
import type { DisputeState } from "@jeflink/api-client";
import { getLocale, getTranslations } from "next-intl/server";

import { Alert } from "@/components/ui/alert";
import { formatDateTime } from "@/lib/requests/format";

export async function DisputeStatus({ dispute }: { dispute: DisputeState }) {
  const t = await getTranslations("bookings.dispute");
  const locale = await getLocale();
  const decision = dispute.status === "resolved" ? dispute.decision : null;
  return (
    <section
      aria-labelledby="dispute-title"
      className="flex flex-col gap-4 rounded-card border border-line bg-surface p-5 sm:p-6"
    >
      <h2 id="dispute-title" className="font-display text-2xl tracking-tight">
        {decision ? t("resolvedTitle") : t("openTitle")}
      </h2>
      <p className="text-base text-ink">
        {t("openedOn", {
          date: formatDateTime(dispute.created_at, locale),
          reason: t(`reasons.${dispute.reason}`),
        })}
      </p>
      {decision ? (
        <Alert tone="info">{t(`decisions.${decision}`)}</Alert>
      ) : (
        <p className="text-base text-ink">{t("examining")}</p>
      )}
      <p className="rounded-card bg-sand p-4 text-base font-medium leading-relaxed text-ink">
        {t("decision")}
      </p>
    </section>
  );
}
