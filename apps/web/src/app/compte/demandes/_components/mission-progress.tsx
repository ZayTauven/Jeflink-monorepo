// Frise de la mission (spec 004, web 1). Question métier : « Où en est le pro, et qu'est-ce que je
// dois faire maintenant ? ». Rendu serveur ; l'actualisation est un petit composant client.
// Chaque étape dit son état en toutes lettres (fait, en ce moment, à venir) : jamais la couleur seule.
import type { ClientBooking } from "@jeflink/api-client";
import { getLocale, getTranslations } from "next-intl/server";

import { CheckIcon, CircleIcon, ClockIcon } from "@/components/ui/icons";
import { isMissionLive, missionSteps } from "@/lib/bookings/steps";
import { formatDeadline } from "@/lib/requests/format";

import { AutoRefresh } from "./auto-refresh";
import { RefreshButton } from "./refresh-button";

export async function MissionProgress({ booking, now }: { booking: ClientBooking; now: string }) {
  const t = await getTranslations("bookings.progress");
  const locale = await getLocale();
  const steps = missionSteps(booking);
  if (!steps) return null;
  const live = isMissionLive(booking.status);

  return (
    <section
      aria-labelledby="progress-title"
      className="flex flex-col gap-4 rounded-card border border-line bg-surface p-5 sm:p-6"
    >
      <h2 id="progress-title" className="font-display text-2xl tracking-tight">
        {t("title")}
      </h2>
      <p aria-live="polite" className="text-lg leading-relaxed text-ink">
        {t(`hint.${booking.status}`)}
      </p>
      <ol className="flex flex-col divide-y divide-line rounded-card border border-line">
        {steps.map((step) => (
          <li
            key={step.key}
            aria-current={step.state === "current" ? "step" : undefined}
            className="flex min-h-12 items-center gap-3 px-4 py-3"
          >
            {step.state === "done" ? (
              <CheckIcon className="size-5 shrink-0 text-success" />
            ) : step.state === "current" ? (
              <ClockIcon className="size-5 shrink-0 text-accent-strong" />
            ) : (
              <CircleIcon className="size-5 shrink-0 text-ink-muted" />
            )}
            <span
              className={`flex-1 text-base ${
                step.state === "current" ? "font-medium text-ink" : "text-ink"
              } ${step.state === "upcoming" ? "text-ink-muted" : ""}`}
            >
              {t(`steps.${step.key}`)}
            </span>
            <span className="text-sm text-ink-muted">
              {step.state === "current"
                ? t("state.current")
                : step.state === "upcoming"
                  ? t("state.upcoming")
                  : step.at
                    ? t("state.doneAt", { when: formatDeadline(step.at, now, locale) })
                    : t("state.done")}
            </span>
          </li>
        ))}
      </ol>
      <div className="flex flex-col gap-2">
        <RefreshButton className="self-start" />
        {live ? <p className="text-sm text-ink-muted">{t("autoNotice")}</p> : null}
      </div>
      <AutoRefresh active={live} />
    </section>
  );
}
