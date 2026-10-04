// /compte/demandes (spec 003, web 2). Question métier : « Où en sont mes demandes ? ». Action
// principale : ouvrir une demande (ou en faire une nouvelle si la liste est vide).
//
// Liste paginée par curseur (`?curseur=`) : jamais tout d'un coup sur un réseau lent. Page
// authentifiée : `private, no-store` posé par le proxy, jamais prérendue (`serverApi`).
import { type PaginatedClientRequestSummaryList, requestsList } from "@jeflink/api-client";
import type { Metadata } from "next";
import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";

import { PageShell } from "@/components/page-shell";
import { StatusBadge } from "@/components/status-badge";
import { Alert } from "@/components/ui/alert";
import { ButtonLink, buttonClass } from "@/components/ui/button";
import { rethrowApiError, serverApiWithSession } from "@/lib/bff";
import { localized } from "@/lib/requests/catalog";
import { formatDay } from "@/lib/requests/format";
import { cursorFromNext, safeCursor } from "@/lib/requests/ids";
import { STATE_TONE, requestState } from "@/lib/requests/status";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("requests.list");
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function RequestsPage({ searchParams }: { searchParams: SearchParams }) {
  const params = await searchParams;
  const cursor = safeCursor(typeof params.curseur === "string" ? params.curseur : undefined);
  const api = await serverApiWithSession();
  const t = await getTranslations("requests");
  const locale = await getLocale();

  let page: PaginatedClientRequestSummaryList | null = null;
  try {
    const response = await requestsList(cursor ? { cursor } : undefined, api.options);
    page = response.status === 200 ? response.data : null;
  } catch (error) {
    if (error instanceof Error && error.name === "ApiError") {
      await rethrowApiError(error, api); // 401 → refresh ou connexion ; sinon relancée
    }
    page = null; // réseau coupé entre le serveur et l'API : état d'erreur, pas une page blanche
  }
  const nextCursor = cursorFromNext(page?.next);

  return (
    <PageShell>
      <header className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col gap-3">
          <h1 className="font-display text-balance text-4xl leading-[1.05] tracking-tight sm:text-5xl">
            {t("list.title")}
          </h1>
          <p className="text-lg leading-relaxed text-ink-muted">{t("list.lead")}</p>
        </div>
        <ButtonLink href="/demande" variant="primary" className="self-start">
          {t("list.new")}
        </ButtonLink>
      </header>

      {page === null ? (
        <Alert
          tone="error"
          action={
            <ButtonLink href="/compte/demandes" variant="secondary" className="self-start">
              {t("list.retry")}
            </ButtonLink>
          }
        >
          {t("list.unavailable")}
        </Alert>
      ) : page.results.length === 0 ? (
        <section className="flex flex-col items-start gap-4 rounded-card border border-line bg-surface p-6 sm:p-8">
          <h2 className="font-display text-2xl tracking-tight">{t("list.empty.title")}</h2>
          <p className="text-base leading-relaxed text-ink-muted">{t("list.empty.lead")}</p>
          <ButtonLink href="/demande" variant="primary">
            {t("list.empty.cta")}
          </ButtonLink>
        </section>
      ) : (
        <>
          <ul className="flex flex-col gap-3">
            {page.results.map((request) => {
              const state = requestState(request.status);
              const trade = localized(request.trade.name, locale);
              return (
                <li key={request.public_id}>
                  <Link
                    href={`/compte/demandes/${request.public_id}`}
                    className="flex min-h-12 flex-col gap-3 rounded-card border border-line bg-surface p-5 hover:border-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-strong"
                  >
                    <span className="flex flex-wrap items-center justify-between gap-3">
                      <span className="text-lg font-medium text-ink">
                        {trade}
                        {request.zone ? ` · ${request.zone.name}` : ""}
                      </span>
                      <StatusBadge tone={state ? STATE_TONE[state] : "neutral"}>
                        {t(`status.${state ?? "unknown"}`)}
                      </StatusBadge>
                    </span>
                    <span className="text-sm text-ink-muted">
                      {t("list.sent", { date: formatDay(request.created_at, locale) })}
                      {request.expires_at &&
                      (request.status === "open" || request.status === "quoted")
                        ? ` · ${t("list.until", { date: formatDay(request.expires_at, locale) })}`
                        : ""}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
          <nav className="mt-8 flex flex-wrap gap-3">
            {nextCursor ? (
              <Link
                href={`/compte/demandes?curseur=${encodeURIComponent(nextCursor)}`}
                className={buttonClass("secondary")}
              >
                {t("list.more")}
              </Link>
            ) : null}
            {cursor ? (
              <Link href="/compte/demandes" className={buttonClass("quiet")}>
                {t("list.newer")}
              </Link>
            ) : null}
          </nav>
        </>
      )}
    </PageShell>
  );
}
