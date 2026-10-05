// Panneaux d'état d'une demande (spec 003, web 2) : attente du pro, réservation confirmée, résumé.
// Rendu serveur : aucune interactivité ici. Le contact du pro n'arrive de l'API qu'à `scheduled`.
import type { ClientBooking, ClientQuote, ClientRequest } from "@jeflink/api-client";
import { getLocale, getTranslations } from "next-intl/server";

import { Alert } from "@/components/ui/alert";
import { ButtonLink } from "@/components/ui/button";
import { RatingLine } from "@/components/rating-line";
import { ChatIcon, PhoneIcon } from "@/components/ui/icons";
import { whatsappUrl } from "@/lib/login/support";
import {
  formatDay,
  formatDeadline,
  formatPhoneDisplay,
  formatXof,
  isE164,
  slotLabel,
} from "@/lib/requests/format";

/** Créneau en langage courant, côté serveur (mêmes mots que `useSlotText`). */
async function slotText(startIso: string, endIso: string, now: string) {
  const t = await getTranslations("requests.quote");
  const locale = await getLocale();
  const label = slotLabel(startIso, endIso, now, locale);
  if (!label) return { text: "", range: "" };
  const period = t(`period.${label.period}`);
  let text: string;
  if (label.day.kind === "today") text = t("slotDay", { day: t("today"), period });
  else if (label.day.kind === "tomorrow") text = t("slotDay", { day: t("tomorrow"), period });
  else if (label.day.kind === "weekday") text = t("slotDay", { day: label.day.text, period });
  else text = t("slotDate", { date: label.day.text, period });
  return { text, range: t("slotRange", { from: label.from, to: label.to }) };
}

/** Attente : le pro a jusqu'à HH:MM (heure de Dakar, pas de compte à rebours). */
export async function WaitingPanel({ booking, now }: { booking: ClientBooking; now: string }) {
  const t = await getTranslations("requests.waiting");
  const locale = await getLocale();
  const slot = await slotText(booking.slot_start, booking.slot_end, now);
  return (
    <section
      aria-labelledby="waiting-title"
      className="flex flex-col gap-4 rounded-card border border-line bg-surface p-5 sm:p-6"
    >
      <h2 id="waiting-title" className="font-display text-2xl tracking-tight">
        {t("title")}
      </h2>
      <p className="text-lg leading-relaxed text-ink">
        {t("lead", {
          name: booking.provider.business_name,
          when: formatDeadline(booking.confirm_deadline, now, locale),
        })}
      </p>
      <p className="text-base text-ink">{t("slot", { slot: slot.text, range: slot.range })}</p>
      <p className="text-base text-ink-muted">{t("notice")}</p>
    </section>
  );
}

/** Réservation confirmée : créneau, pro, appel et WhatsApp, mention de paiement. */
export async function BookedPanel({
  booking,
  quote,
  now,
}: {
  booking: ClientBooking;
  quote: ClientQuote | undefined;
  now: string;
}) {
  const t = await getTranslations("requests.booked");
  const slot = await slotText(booking.slot_start, booking.slot_end, now);
  const contact = booking.contact;
  const phone = contact && isE164(contact.phone) ? contact.phone : null;
  const name = contact?.business_name ?? booking.provider.business_name;
  const wa = phone
    ? whatsappUrl(phone, t("whatsappMessage", { slot: slot.text, range: slot.range }))
    : null;

  return (
    <section
      aria-labelledby="booked-title"
      className="flex flex-col gap-5 rounded-card border border-line bg-surface p-5 sm:p-6"
    >
      <h2 id="booked-title" className="font-display text-2xl tracking-tight">
        {t("title")}
      </h2>
      <dl className="grid gap-4 sm:grid-cols-2">
        <div>
          <dt className="text-sm text-ink-muted">{t("slot")}</dt>
          <dd className="text-lg font-medium text-ink">{slot.text}</dd>
          <dd className="text-base text-ink-muted">{slot.range}</dd>
        </div>
        <div>
          <dt className="text-sm text-ink-muted">{t("pro")}</dt>
          <dd className="text-lg font-medium text-ink">{name}</dd>
          <dd>
            <RatingLine rating={booking.provider.rating} />
          </dd>
          {phone ? (
            <dd className="text-base text-ink-muted">
              {t("phoneLine", { number: formatPhoneDisplay(phone) })}
            </dd>
          ) : null}
        </div>
        <div>
          <dt className="text-sm text-ink-muted">{t("amount")}</dt>
          <dd className="text-lg font-medium text-ink">{formatXof(booking.amount_xof)}</dd>
          {booking.original_amount_xof !== booking.amount_xof ? (
            <dd className="text-base text-ink-muted">
              {t("originalAmount", { amount: formatXof(booking.original_amount_xof) })}
            </dd>
          ) : null}
          {quote?.kind === "visit" ? (
            <dd className="text-base text-ink-muted">{t("visitReminder")}</dd>
          ) : null}
        </div>
      </dl>

      {phone ? (
        <div className="flex flex-col gap-3 sm:flex-row">
          <ButtonLink href={`tel:${phone}`} variant="primary">
            <PhoneIcon className="size-5" />
            {t("call", { name })}
          </ButtonLink>
          {wa ? (
            <ButtonLink href={wa} target="_blank" rel="noopener noreferrer" variant="secondary">
              <ChatIcon className="size-5" />
              {t("whatsapp")}
              <span className="sr-only"> {name}</span>
            </ButtonLink>
          ) : null}
        </div>
      ) : (
        <Alert tone="info">{t("noContact")}</Alert>
      )}

      <p className="rounded-card bg-sand p-4 text-base font-medium leading-relaxed text-ink">
        {t("payment")}
      </p>
    </section>
  );
}

/** Résumé de ce que le client a demandé. Ses propres données : repère et description compris. */
export async function RequestSummary({ request }: { request: ClientRequest }) {
  const t = await getTranslations("requests");
  const locale = await getLocale();
  const s = (key: string, values?: Record<string, string>) => t(`detail.summary.${key}`, values);
  const when =
    request.preferred_when === "date" && request.preferred_date
      ? s("dateAt", {
          date: formatDay(`${request.preferred_date}T12:00:00Z`, locale),
          period: t(`form.when.${request.preferred_period}`).toLowerCase(),
        })
      : s("asap");
  const rows: [string, string][] = [];
  if (request.service) {
    const { fr, wo } = request.service.name;
    rows.push([s("service"), locale === "wo" && wo ? wo : fr]);
  }
  if (request.zone) rows.push([s("zone"), request.zone.name]);
  if (request.landmark) rows.push([s("landmark"), request.landmark]);
  if (request.has_location) rows.push([s("position"), s("positionShared")]);
  if (request.description) rows.push([s("description"), request.description]);
  rows.push([s("when"), request.urgent ? `${when} · ${s("urgent")}` : when]);

  return (
    <section aria-labelledby="summary-title" className="flex flex-col gap-4">
      <h2 id="summary-title" className="font-display text-2xl tracking-tight">
        {s("title")}
      </h2>
      <dl className="flex flex-col divide-y divide-line rounded-card border border-line bg-surface">
        {rows.map(([label, value]) => (
          <div key={label} className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:gap-6">
            <dt className="text-sm text-ink-muted sm:w-40 sm:shrink-0">{label}</dt>
            <dd className="whitespace-pre-line break-words text-base text-ink">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
