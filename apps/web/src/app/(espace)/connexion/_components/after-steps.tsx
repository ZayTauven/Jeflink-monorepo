"use client";

// Étapes après le code (spec 001, « Client, première connexion » 3 et 4, T2, S18) et écrans
// sans impasse (T3). Chaque écran répond à une seule question, avec une action principale.
import type { OtherSession } from "@jeflink/api-client";
import { useLocale, useTranslations } from "next-intl";
import { type FormEvent, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { PhoneIcon, ScreenIcon } from "@/components/ui/icons";
import type { LoginError } from "@/lib/login/errors";

import { StepHeader } from "./step-header";
import { LoginErrorAlert, SupportLink } from "./support";

/** « il y a 3 jours », « hier », « il y a 2 heures » : heure de Dakar sans objet ici (durée). */
function since(iso: string, locale: string): string {
  const seconds = (Date.parse(iso) - Date.now()) / 1000;
  const format = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  if (!Number.isFinite(seconds)) return "";
  const abs = Math.abs(seconds);
  if (abs < 3600) return format.format(Math.round(seconds / 60), "minute");
  if (abs < 86400) return format.format(Math.round(seconds / 3600), "hour");
  return format.format(Math.round(seconds / 86400), "day");
}

/** « Autres appareils » (T2) : question « Déconnecter ces téléphones ? ». */
export function OthersStep({
  sessions,
  onAnswer,
  pending,
  error,
}: {
  sessions: OtherSession[];
  onAnswer: (revoke: boolean) => void;
  pending: boolean;
  error: LoginError | null;
}) {
  const t = useTranslations("connexion.others");
  const locale = useLocale();
  const count = sessions.length;
  return (
    <div className="flex flex-col gap-8">
      <StepHeader title={t("title")}>
        <p>{t("lead", { count })}</p>
      </StepHeader>
      <ul className="flex flex-col divide-y divide-line rounded-card border border-line bg-surface">
        {sessions.map((session) => (
          <li key={session.public_id} className="flex items-center gap-4 px-4 py-4">
            <span className="flex size-12 shrink-0 items-center justify-center rounded-pill bg-sand text-ink">
              {session.app === "web" || session.app === "console" ? (
                <ScreenIcon className="size-6" />
              ) : (
                <PhoneIcon className="size-6" />
              )}
            </span>
            <span className="flex flex-col">
              <span className="font-medium text-ink">
                {session.device_label || t("unknownDevice")}
              </span>
              <span className="text-sm text-ink-muted">
                {t("seen", { when: since(session.last_seen_at, locale) })}
              </span>
            </span>
          </li>
        ))}
      </ul>
      <p className="text-base text-ink">{t("question", { count })}</p>
      {error ? <LoginErrorAlert error={error} /> : null}
      <div className="flex flex-col gap-3 sm:flex-row">
        <Button
          onClick={() => onAnswer(true)}
          disabled={pending}
          aria-busy={pending}
          className="flex-1"
        >
          {t("yes")}
        </Button>
        <Button
          variant="secondary"
          onClick={() => onAnswer(false)}
          disabled={pending}
          className="flex-1"
        >
          {t("no")}
        </Button>
      </div>
    </div>
  );
}

/** Compte dormant (S18) : « Repartir de zéro » par défaut, ou le support pour le retrouver. */
export function DormantStep({
  onFreshStart,
  pending,
  error,
}: {
  onFreshStart: () => void;
  pending: boolean;
  error: LoginError | null;
}) {
  const t = useTranslations("connexion.dormant");
  return (
    <div className="flex flex-col gap-8">
      <StepHeader title={t("title")}>
        <p>{t("lead")}</p>
      </StepHeader>
      {error ? <LoginErrorAlert error={error} /> : null}
      <div className="flex flex-col gap-3">
        <p className="text-base text-ink">{t("freshHint")}</p>
        <Button onClick={onFreshStart} disabled={pending} aria-busy={pending} className="w-full">
          {t("fresh")}
        </Button>
      </div>
      <div className="flex flex-col gap-3 border-t border-line pt-6">
        <p className="text-base text-ink">{t("mineHint")}</p>
        <SupportLink message={t("mineMessage")} label={t("mine")} />
      </div>
    </div>
  );
}

/** Nouveau compte : « Comment doit-on vous appeler ? » ; « Plus tard » garde un compte invité. */
export function NameStep({
  onSave,
  onSkip,
  pending,
  error,
}: {
  onSave: (name: string) => void;
  onSkip: () => void;
  pending: boolean;
  error: LoginError | null;
}) {
  const t = useTranslations("connexion.name");
  const inputId = useId();
  const [name, setName] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (name.trim().length >= 2 && !pending) onSave(name.trim());
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-8" noValidate>
      <StepHeader title={t("title")}>
        <p>{t("lead")}</p>
      </StepHeader>
      <div className="flex flex-col gap-2">
        <label htmlFor={inputId} className="text-sm font-medium text-ink">
          {t("label")}
        </label>
        <input
          id={inputId}
          type="text"
          autoComplete="name"
          maxLength={80}
          value={name}
          onChange={(event) => setName(event.target.value)}
          className="min-h-14 w-full rounded-card border border-line-strong bg-surface px-4 text-lg text-ink outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-strong"
        />
      </div>
      {error ? <LoginErrorAlert error={error} /> : null}
      <div className="flex flex-col gap-3 sm:flex-row">
        <Button type="submit" disabled={pending} aria-busy={pending} className="flex-1">
          {pending ? t("saving") : t("submit")}
        </Button>
        <Button variant="secondary" onClick={onSkip} disabled={pending} className="flex-1">
          {t("later")}
        </Button>
      </div>
    </form>
  );
}

/** Numéro hors régions couvertes (T3) : un écran, pas une erreur en ligne. */
export function RegionStep({ onBack }: { onBack: () => void }) {
  const t = useTranslations("connexion.region");
  return (
    <div className="flex flex-col gap-8">
      <StepHeader title={t("title")}>
        <p>{t("lead")}</p>
      </StepHeader>
      <div className="flex flex-col gap-3">
        <SupportLink label={t("support")} variant="primary" />
        <SupportLink label={t("notify")} message={t("notifyMessage")} />
        <Button variant="quiet" onClick={onBack}>
          {t("back")}
        </Button>
      </div>
    </div>
  );
}

/** Compte de l'équipe (second facteur exigé) : il se connecte sur la console. */
export function StaffStep({ onBack }: { onBack: () => void }) {
  const t = useTranslations("connexion");
  return (
    <div className="flex flex-col gap-8">
      <StepHeader title={t("mfa.title")}>
        <p>{t("mfa.lead")}</p>
      </StepHeader>
      <Button variant="quiet" onClick={onBack}>
        {t("region.back")}
      </Button>
    </div>
  );
}
