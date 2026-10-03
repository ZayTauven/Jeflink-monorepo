// /compte/demandes/[id] (spec 003, web 2). Question métier : « Que se passe-t-il pour ma demande,
// et que dois-je faire maintenant ? ». Une seule action principale selon l'état : choisir un devis,
// attendre le pro, ou joindre le pro.
//
// Un seul appel pour la demande, ses devis, sa réservation et le désistement du pro (réseau faible). L'identifiant est
// validé en UUID avant tout appel ; une demande d'un autre compte répond 404.
import { type ClientRequest, requestsRetrieve } from "@jeflink/api-client";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getLocale, getTranslations } from "next-intl/server";

import { PageShell } from "@/components/page-shell";
import { StatusBadge } from "@/components/status-badge";
import { SupportLink } from "@/components/support-link";
import { Alert } from "@/components/ui/alert";
import { ButtonLink } from "@/components/ui/button";
import { ArrowLeftIcon } from "@/components/ui/icons";
import { rethrowApiError, serverApiWithSession } from "@/lib/bff";
import { localized } from "@/lib/requests/catalog";
import { formatDay } from "@/lib/requests/format";
import { isUuid } from "@/lib/requests/ids";
import { choosableQuotes, sortQuotes } from "@/lib/requests/quotes";
import { STATE_TONE, canCancelRequest, requestState } from "@/lib/requests/status";
import { readSiteConfig } from "@/lib/site-config";

import { CancelPanel } from "../_components/cancel-panel";
import { BookedPanel, RequestSummary, WaitingPanel } from "../_components/detail-panels";
import { QuotePicker } from "../_components/quote-picker";
import { RefreshButton } from "../_components/refresh-button";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("requests.detail");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

export default async function RequestDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isUuid(id)) notFound();
  const api = await serverApiWithSession();
  const t = await getTranslations("requests");
  const locale = await getLocale();

  let request: ClientRequest;
  try {
    const response = await requestsRetrieve(id, api.options);
    if (response.status !== 200) notFound();
    request = response.data;
  } catch (error) {
    if (error instanceof Error && error.name === "ApiError") {
      if ((error as Error & { status?: number }).status === 404) notFound();
      return rethrowApiError(error, api);
    }
    throw error; // coupure entre le serveur et l'API : error.tsx, avec « Réessayer »
  }

  const now = new Date().toISOString();
  const state = requestState(request.status);
  const trade = localized(request.trade.name, locale);
  const quotes = sortQuotes(choosableQuotes(request.quotes));
  const booking = request.booking;
  const { supportWhatsapp } = readSiteConfig(process.env);
  const awaiting = request.status === "booked" && booking?.status === "accepted";
  const statusKey = awaiting ? "awaiting" : (state ?? "unknown");
  const live = request.status === "open" || request.status === "quoted";
  const withdrew = live && request.withdrawn_by_provider;

  return (
    <PageShell>
      <Link
        href="/compte/demandes"
        className="mb-6 inline-flex min-h-12 items-center gap-2 text-base font-medium text-accent-strong underline underline-offset-4 hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-strong"
      >
        <ArrowLeftIcon className="size-5" />
        {t("detail.back")}
      </Link>

      <header className="mb-8 flex flex-col gap-3">
        <h1 className="font-display text-balance text-4xl leading-[1.05] tracking-tight sm:text-5xl">
          {trade}
          {request.zone ? ` · ${request.zone.name}` : ""}
        </h1>
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge tone={awaiting ? "info" : state ? STATE_TONE[state] : "neutral"}>
            {t(`status.${statusKey}`)}
          </StatusBadge>
          <span className="text-sm text-ink-muted">
            {t("detail.summary.sent", { date: formatDay(request.created_at, locale) })}
          </span>
        </div>
      </header>

      <div className="flex flex-col gap-10">
        {request.status === "needs_zone" ? (
          <Alert
            tone="info"
            action={
              <SupportLink
                number={supportWhatsapp}
                message={t("detail.needsZone.supportMessage")}
                label={t("detail.needsZone.support")}
                className="self-start"
              />
            }
          >
            <p className="font-medium">{t("detail.needsZone.title")}</p>
            <p>{t("detail.needsZone.lead")}</p>
          </Alert>
        ) : null}

        {withdrew ? (
          <Alert tone="info">
            {quotes.length > 0 ? t("detail.quotes.withdrew") : t("detail.quotes.withdrewNone")}
          </Alert>
        ) : null}

        {request.status === "open" && quotes.length === 0 ? (
          <section className="flex flex-col items-start gap-4 rounded-card border border-line bg-surface p-5 sm:p-6">
            <h2 className="font-display text-2xl tracking-tight">{t("detail.open.title")}</h2>
            <p className="text-base leading-relaxed text-ink-muted">{t("detail.open.lead")}</p>
            {request.expires_at ? (
              <p className="text-sm text-ink-muted">
                {t("detail.open.until", { date: formatDay(request.expires_at, locale) })}
              </p>
            ) : null}
            <RefreshButton />
          </section>
        ) : null}

        {live && quotes.length > 0 ? (
          <section aria-labelledby="quotes-title" className="flex flex-col gap-5">
            <div className="flex flex-col gap-2">
              <h2 id="quotes-title" className="font-display text-2xl tracking-tight">
                {t("detail.quotes.title", { count: quotes.length })}
              </h2>
              <p className="text-base leading-relaxed text-ink-muted">{t("detail.quotes.lead")}</p>
              <p className="text-base font-medium text-ink">{t("detail.quotes.contactNotice")}</p>
            </div>
            <QuotePicker quotes={quotes} now={now} />
            <RefreshButton className="self-start" />
          </section>
        ) : null}

        {request.status === "booked" && booking ? (
          booking.status === "accepted" ? (
            <>
              <WaitingPanel booking={booking} now={now} />
              <RefreshButton className="self-start" />
            </>
          ) : (
            <BookedPanel
              booking={booking}
              quote={request.quotes.find((quote) => quote.public_id === booking.quote)}
              now={now}
            />
          )
        ) : null}

        {request.status === "booked" && !booking ? <RefreshButton className="self-start" /> : null}

        {request.status === "cancelled" || request.status === "expired" ? (
          <section className="flex flex-col items-start gap-4 rounded-card border border-line bg-surface p-5 sm:p-6">
            <h2 className="font-display text-2xl tracking-tight">
              {t(`closed.${request.status}.title`)}
            </h2>
            <p className="text-base leading-relaxed text-ink-muted">
              {t(`closed.${request.status}.lead`)}
            </p>
            <ButtonLink href="/demande" variant="primary">
              {t("closed.new")}
            </ButtonLink>
          </section>
        ) : null}

        <RequestSummary request={request} />

        {canCancelRequest(request.status) ? (
          <CancelPanel kind="request" id={request.public_id} />
        ) : null}
        {booking && (booking.status === "accepted" || booking.status === "scheduled") ? (
          <CancelPanel kind="booking" id={booking.public_id} />
        ) : null}
      </div>
    </PageShell>
  );
}
