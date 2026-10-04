// Corps de la page d'une réservation après la confirmation du pro (spec 004, web 1 à 3). Question
// métier : « Où en est la mission, et que dois-je faire maintenant ? ». L'ordre suit l'urgence :
// un prix à décider, le code à donner, puis le suivi, les photos, la fin. Rendu serveur ; les
// panneaux interactifs sont des composants client qui reçoivent des données déjà prêtes.
import type { ClientBooking, ClientQuote } from "@jeflink/api-client";
import { getLocale, getTranslations } from "next-intl/server";

import { SupportLink } from "@/components/support-link";
import { Alert } from "@/components/ui/alert";
import { pendingAmendment } from "@/lib/bookings/amendments";
import { isCodeStage, isMission, isMissionLive } from "@/lib/bookings/steps";
import { whatsappUrl } from "@/lib/login/support";
import { formatDeadline, isE164 } from "@/lib/requests/format";

import { AmendmentCard } from "./amendment-card";
import { CompletionCodeCard } from "./completion-code-card";
import { BookedPanel } from "./detail-panels";
import { DisputeStatus } from "./dispute-status";
import { FinishPanel } from "./finish-panel";
import { MissionProgress } from "./mission-progress";
import { NoShowPanel } from "./no-show-panel";
import { PhotoGallery } from "./photo-gallery";

export async function MissionPanels({
  booking,
  quote,
  requestId,
  now,
  supportWhatsapp,
}: {
  booking: ClientBooking;
  quote: ClientQuote | undefined;
  requestId: string;
  now: string;
  supportWhatsapp: string | null;
}) {
  const t = await getTranslations("bookings");
  const locale = await getLocale();
  const supportHref = whatsappUrl(
    supportWhatsapp,
    t("problem.message", { reference: booking.public_id }),
  );

  // Réservation annulée (par le pro, l'Ops ou le système) : affichage neutre, sans reproche.
  if (booking.status === "cancelled") {
    return (
      <section className="flex flex-col items-start gap-4 rounded-card border border-line bg-surface p-5 sm:p-6">
        <h2 className="font-display text-2xl tracking-tight">
          {t(booking.cancelled_by === "ops" ? "cancelled.opsTitle" : "cancelled.title")}
        </h2>
        <p className="text-base leading-relaxed text-ink-muted">
          {t(booking.cancelled_by === "ops" ? "cancelled.opsLead" : "cancelled.lead")}
        </p>
        <SupportLink
          number={supportWhatsapp}
          message={t("problem.message", { reference: booking.public_id })}
          label={t("common.writeSupport")}
        />
      </section>
    );
  }

  if (!isMission(booking.status)) return <BookedPanel booking={booking} quote={quote} now={now} />;

  const amendment = pendingAmendment(booking.amendments);
  const phone = booking.contact && isE164(booking.contact.phone) ? booking.contact.phone : null;
  const providerName = booking.contact?.business_name ?? booking.provider.business_name;
  const live = isMissionLive(booking.status);
  const beforeSlotEnd =
    (booking.status === "scheduled" || booking.status === "en_route") &&
    !booking.can_report_no_show &&
    Date.parse(booking.no_show_available_at) > Date.parse(now);
  const afterWork =
    booking.status === "completed" || booking.status === "disputed" || booking.status === "closed";

  return (
    <>
      {amendment && booking.status === "in_progress" ? (
        <AmendmentCard
          bookingId={booking.public_id}
          amendment={amendment}
          supportHref={supportHref}
        />
      ) : null}

      {isCodeStage(booking.status) ? (
        <CompletionCodeCard
          bookingId={booking.public_id}
          code={booking.completion_code}
          locked={booking.completion_code_locked}
          canRegenerate={booking.can_regenerate_completion_code}
          canSendSms={booking.can_send_completion_code_sms}
          supportHref={supportHref}
        />
      ) : null}

      <MissionProgress booking={booking} now={now} />

      {booking.can_report_no_show ? (
        <NoShowPanel
          bookingId={booking.public_id}
          requestId={requestId}
          providerName={providerName}
          phone={phone}
          supportHref={supportHref}
        />
      ) : beforeSlotEnd ? (
        <p className="text-base text-ink-muted">
          {t("noShow.availableAt", {
            when: formatDeadline(booking.no_show_available_at, now, locale),
          })}
        </p>
      ) : null}

      <BookedPanel booking={booking} quote={quote} now={now} />

      <PhotoGallery
        bookingId={booking.public_id}
        photos={booking.photos}
        now={now}
        supportHref={supportHref}
      />

      {afterWork && booking.dispute ? <DisputeStatus dispute={booking.dispute} /> : null}

      {afterWork ? (
        <FinishPanel
          bookingId={booking.public_id}
          status={booking.status}
          canDispute={booking.can_dispute}
          canReview={booking.can_review}
          hasDispute={booking.dispute !== null}
          disputeDeadline={booking.dispute_deadline}
          deadlineText={
            booking.dispute_deadline ? formatDeadline(booking.dispute_deadline, now, locale) : ""
          }
          reviewUntilText={
            booking.review_deadline ? formatDeadline(booking.review_deadline, now, locale) : ""
          }
          now={now}
          review={booking.review}
          supportHref={supportHref}
        />
      ) : null}

      {live ? (
        <section
          aria-labelledby="problem-title"
          className="flex flex-col items-start gap-3 rounded-card border border-line bg-surface p-5 sm:p-6"
        >
          <h2 id="problem-title" className="font-display text-2xl tracking-tight">
            {t("problem.title")}
          </h2>
          <p className="text-base leading-relaxed text-ink-muted">{t("problem.lead")}</p>
          {supportHref ? (
            <SupportLink
              number={supportWhatsapp}
              message={t("problem.message", { reference: booking.public_id })}
              label={t("problem.cta")}
            />
          ) : (
            <Alert tone="info">{t("problem.noSupport")}</Alert>
          )}
        </section>
      ) : null}
    </>
  );
}
