"use client";

// Formulaire de demande (spec 003, web 1). Un écran, une question : « Que faut-il faire, où, et
// quand ? ». Réseau faible : le brouillon survit à une coupure (localStorage, sans la position),
// la clé d'idempotence est gardée pour les nouvelles tentatives, et rejouée telle quelle avec le
// quartier choisi après `zone_ambiguous`.
import { refreshWebSession } from "@jeflink/api-client/web";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";

import { SupportLink } from "@/components/support-link";
import { Alert } from "@/components/ui/alert";
import { Button, ButtonLink } from "@/components/ui/button";
import { Choice, Field, Fieldset, describedBy, inputClass } from "@/components/ui/form";
import { reconcileDraft } from "@/lib/requests/catalog";
import {
  type Draft,
  type Period,
  browserStorage,
  clearDraft,
  emptyDraft,
  loadDraft,
  newIdempotencyKey,
  saveDraft,
} from "@/lib/requests/draft";
import type { Candidate, RequestError } from "@/lib/requests/errors";
import { dakarToday } from "@/lib/requests/format";
import {
  type FieldErrors,
  type Location,
  MAX_DESCRIPTION,
  MAX_LANDMARK,
  hasErrors,
  validateDraft,
  withZoneChoice,
} from "@/lib/requests/payload";
import { callAction } from "@/lib/requests/result";
import type { TradeOption, ZoneOption } from "@/lib/requests/search";

import { createRequestAction } from "../actions";
import { LocationField } from "./location-field";
import { TradePicker, ZonePicker } from "./pickers";

const PERIODS: Period[] = ["morning", "afternoon", "evening", "any"];
const UNSERVED = new Set(["trade_not_in_zone", "out_of_area", "zone_inactive", "trade_inactive"]);

export function RequestForm({
  trades,
  zones,
  profileComplete,
  supportWhatsapp,
}: {
  trades: TradeOption[];
  zones: ZoneOption[];
  profileComplete: boolean;
  supportWhatsapp: string | null;
}) {
  const t = useTranslations("requests");
  const router = useRouter();
  const formId = useId();
  const summaryRef = useRef<HTMLDivElement>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [location, setLocation] = useState<Location | null>(null);
  const [extraZones, setExtraZones] = useState<ZoneOption[]>([]);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<RequestError | null>(null);
  const [ambiguous, setAmbiguous] = useState<Candidate[] | null>(null);
  const [restored, setRestored] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);
  const [today] = useState(() => dakarToday());

  // Brouillon : relu une fois montée (jamais au rendu serveur), puis sauvegardé à chaque saisie.
  useEffect(() => {
    const saved = loadDraft(browserStorage());
    if (saved) {
      setDraft(reconcileDraft(saved, trades, zones));
      setRestored(true);
    }
    setHydrated(true);
  }, [trades, zones]);

  useEffect(() => {
    if (!hydrated || done) return;
    const timer = setTimeout(() => saveDraft(browserStorage(), draft), 400);
    return () => clearTimeout(timer);
  }, [draft, hydrated, done]);

  const update = (patch: Partial<Draft>) => {
    setDraft((current) => ({ ...current, ...patch }));
    setFieldErrors({});
  };

  const reset = () => {
    clearDraft(browserStorage());
    setDraft(emptyDraft());
    setLocation(null);
    setRestored(false);
    setFieldErrors({});
    setError(null);
    setAmbiguous(null);
  };

  const focusSummary = () => queueMicrotask(() => summaryRef.current?.focus());

  async function submit(current: Draft) {
    if (pending || done) return;
    const errors = validateDraft(current, {
      hasLocation: location !== null,
      profileComplete,
      today,
    });
    setFieldErrors(errors);
    if (hasErrors(errors)) {
      setError(null);
      focusSummary();
      return;
    }
    // Une clé par demande, gardée tant qu'elle n'a pas abouti : un nouvel essai après une
    // coupure ne crée pas de doublon.
    const key = current.idempotencyKey || newIdempotencyKey();
    const next = { ...current, idempotencyKey: key };
    setDraft(next);
    saveDraft(browserStorage(), next);
    setPending(true);
    setError(null);
    setAmbiguous(null);

    const result = await callAction(
      () =>
        createRequestAction({
          draft: profileComplete ? { ...next, displayName: "" } : next,
          location,
          idempotencyKey: key,
        }),
      refreshWebSession,
    );

    if (result.ok) {
      setDone(true);
      clearDraft(browserStorage());
      router.push(`/compte/demandes/${encodeURIComponent(result.data.id)}`);
      return; // `pending` reste vrai : pas de second envoi pendant la navigation
    }
    setPending(false);
    const info = result.error;
    if (info.rotateKey) setDraft((c) => ({ ...c, idempotencyKey: newIdempotencyKey() }));
    if (info.candidates?.length) {
      setAmbiguous(info.candidates);
      setExtraZones(
        info.candidates.map((c) => ({ slug: c.slug, name: c.name, city: "", aliases: [] })),
      );
      focusSummary();
      return;
    }
    setError(info);
    focusSummary();
  }

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void submit(draft);
  };

  const chooseZone = (slug: string) => {
    const next = withZoneChoice(draft, slug);
    setDraft(next);
    void submit(next); // même clé d'idempotence, quartier choisi
  };

  const selectedTrade = trades.find((trade) => trade.slug === draft.tradeSlug);
  const allZones = [...zones, ...extraZones.filter((x) => !zones.some((z) => z.slug === x.slug))];
  const zoneName = allZones.find((zone) => zone.slug === draft.zoneSlug)?.name ?? draft.zoneText;
  const descriptionOptional = draft.serviceSlug !== "";
  const descriptionId = `${formId}-description`;
  const landmarkId = `${formId}-landmark`;
  const nameId = `${formId}-name`;
  const dateId = `${formId}-date`;
  const fe = (key: keyof FieldErrors) => {
    const code = fieldErrors[key];
    return code ? t(`form.errors.${code}`) : undefined;
  };

  const errorLink = error
    ? error.login
      ? { href: "/connexion?next=%2Fdemande", label: t("form.relogin") }
      : error.code === "request_limit_reached" || error.code === "idempotency_key_reused"
        ? { href: "/compte/demandes", label: t("shell.mine") }
        : null
    : null;
  const supportMessage =
    error && UNSERVED.has(error.code)
      ? t("support.unserved", { trade: selectedTrade?.name ?? "", zone: zoneName })
      : t("support.message");

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-10">
      {restored ? (
        <Alert
          tone="info"
          action={
            <Button variant="quiet" onClick={reset} className="self-start px-0">
              {t("form.draftReset")}
            </Button>
          }
        >
          {t("form.draftRestored")}
        </Alert>
      ) : null}

      <div ref={summaryRef} tabIndex={-1} className="flex flex-col gap-4 outline-none">
        {hasErrors(fieldErrors) ? <Alert tone="error">{t("form.summary")}</Alert> : null}
        {error ? (
          <Alert
            tone="error"
            action={
              <div className="flex flex-wrap gap-3">
                {errorLink ? (
                  <ButtonLink href={errorLink.href} variant="secondary">
                    {errorLink.label}
                  </ButtonLink>
                ) : null}
                {error.support ? (
                  <SupportLink
                    number={supportWhatsapp}
                    message={supportMessage}
                    label={t("support.link")}
                  />
                ) : null}
              </div>
            }
          >
            {t(`errors.${error.key}`, error.values)}
          </Alert>
        ) : null}
        {ambiguous ? (
          <Alert tone="info">
            <div className="flex flex-col gap-3">
              <p className="font-medium">{t("form.ambiguous.title")}</p>
              <p>{t("form.ambiguous.lead")}</p>
              <div className="flex flex-wrap gap-3">
                {ambiguous.map((candidate) => (
                  <Button
                    key={candidate.slug}
                    variant="secondary"
                    disabled={pending}
                    onClick={() => chooseZone(candidate.slug)}
                  >
                    {t("form.ambiguous.choose", { name: candidate.name })}
                  </Button>
                ))}
              </div>
            </div>
          </Alert>
        ) : null}
      </div>

      <section className="flex flex-col gap-8">
        <TradePicker
          trades={trades}
          tradeSlug={draft.tradeSlug}
          serviceSlug={draft.serviceSlug}
          onChange={(value) => update(value)}
          error={fe("trade")}
        />
        <ZonePicker
          zones={allZones}
          zoneSlug={draft.zoneSlug}
          otherZone={draft.otherZone}
          zoneText={draft.zoneText}
          onChange={(value) => update(value)}
          error={fe("zone")}
        />
      </section>

      <section className="flex flex-col gap-4">
        <Field
          id={landmarkId}
          label={t("form.landmark.label")}
          hint={t("form.landmark.hint")}
          error={fe("landmark")}
        >
          <input
            id={landmarkId}
            type="text"
            maxLength={MAX_LANDMARK}
            autoComplete="off"
            value={draft.landmark}
            placeholder={t("form.landmark.placeholder")}
            aria-invalid={fieldErrors.landmark ? true : undefined}
            aria-describedby={describedBy(landmarkId, {
              hint: true,
              error: Boolean(fieldErrors.landmark),
            })}
            onChange={(event) => update({ landmark: event.target.value })}
            className={inputClass}
          />
        </Field>
        <p className="text-sm font-medium text-ink">{t("form.landmark.privacy")}</p>
        <LocationField location={location} onChange={setLocation} />
      </section>

      <Field
        id={descriptionId}
        label={
          descriptionOptional ? t("form.description.labelOptional") : t("form.description.label")
        }
        error={fe("description")}
      >
        <textarea
          id={descriptionId}
          rows={4}
          maxLength={MAX_DESCRIPTION}
          value={draft.description}
          placeholder={t("form.description.placeholder")}
          aria-invalid={fieldErrors.description ? true : undefined}
          aria-describedby={describedBy(descriptionId, { error: Boolean(fieldErrors.description) })}
          onChange={(event) => update({ description: event.target.value })}
          className={inputClass}
        />
      </Field>

      <section className="flex flex-col gap-4">
        <Fieldset id={`${formId}-when`} legend={t("form.when.legend")}>
          <div className="flex flex-col gap-2">
            <Choice
              name={`${formId}-when`}
              value="asap"
              checked={draft.when === "asap"}
              onChange={() => update({ when: "asap" })}
            >
              {t("form.when.asap")}
            </Choice>
            <Choice
              name={`${formId}-when`}
              value="date"
              checked={draft.when === "date"}
              onChange={() => update({ when: "date" })}
            >
              {t("form.when.date")}
            </Choice>
          </div>
        </Fieldset>
        {draft.when === "date" ? (
          <div className="flex flex-col gap-4">
            <Field id={dateId} label={t("form.when.dateLabel")} error={fe("date")}>
              <input
                id={dateId}
                type="date"
                min={today}
                value={draft.date}
                suppressHydrationWarning
                aria-invalid={fieldErrors.date ? true : undefined}
                aria-describedby={describedBy(dateId, { error: Boolean(fieldErrors.date) })}
                onChange={(event) => update({ date: event.target.value })}
                className={inputClass}
              />
            </Field>
            <Fieldset id={`${formId}-period`} legend={t("form.when.periodLegend")}>
              <div className="grid gap-2 sm:grid-cols-2">
                {PERIODS.map((period) => (
                  <Choice
                    key={period}
                    name={`${formId}-period`}
                    value={period}
                    checked={draft.period === period}
                    onChange={() => update({ period })}
                  >
                    {t(`form.when.${period}`)}
                  </Choice>
                ))}
              </div>
            </Fieldset>
          </div>
        ) : null}
        <Choice
          type="checkbox"
          checked={draft.urgent}
          onChange={(urgent) => update({ urgent })}
          description={t("form.urgent.hint")}
        >
          {t("form.urgent.label")}
        </Choice>
      </section>

      {!profileComplete ? (
        <Field
          id={nameId}
          label={t("form.name.label")}
          hint={t("form.name.hint")}
          error={fe("displayName")}
        >
          <input
            id={nameId}
            type="text"
            maxLength={256}
            autoComplete="name"
            value={draft.displayName}
            aria-invalid={fieldErrors.displayName ? true : undefined}
            aria-describedby={describedBy(nameId, {
              hint: true,
              error: Boolean(fieldErrors.displayName),
            })}
            onChange={(event) => update({ displayName: event.target.value })}
            className={inputClass}
          />
        </Field>
      ) : null}

      <Button
        type="submit"
        disabled={pending}
        aria-busy={pending}
        className="w-full sm:w-auto sm:self-start"
      >
        {pending ? t("form.sending") : t("form.submit")}
      </Button>
    </form>
  );
}
