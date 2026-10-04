"use client";

// Comparaison des devis (spec 003, web 2). Question : « Quel pro choisir ? ». Une carte par devis,
// classés par créneau (jamais par prix), prix affiché avant le choix. L'acceptation passe par une
// étape de confirmation dans la page (pas de `window.confirm`), puis la page affiche l'attente.
import { refreshWebSession } from "@jeflink/api-client/web";
import type { ClientQuote } from "@jeflink/api-client";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { RatingLine } from "@/components/rating-line";
import { CheckIcon, ChevronDownIcon, ClockIcon } from "@/components/ui/icons";
import type { RequestError } from "@/lib/requests/errors";
import { formatDay, formatXof } from "@/lib/requests/format";
import { readableLabel, sortQuotes } from "@/lib/requests/quotes";
import { callAction } from "@/lib/requests/result";

import { acceptQuoteAction } from "../actions";
import { RefreshButton } from "./refresh-button";
import { useSlotText } from "./use-slot-text";

function QuoteCard({
  quote,
  now,
  busy,
  children,
}: {
  quote: ClientQuote;
  now: string;
  busy: boolean;
  children: React.ReactNode;
}) {
  const t = useTranslations("requests.quote");
  const locale = useLocale();
  const slot = useSlotText(now)(quote.slot_start, quote.slot_end);
  const titleId = `quote-${quote.public_id}`;
  return (
    <li>
      <article
        aria-labelledby={titleId}
        aria-busy={busy}
        className="flex flex-col gap-4 rounded-card border border-line bg-surface p-5 sm:p-6"
      >
        <div className="flex flex-col gap-1">
          <p className="font-display text-4xl leading-none tracking-tight text-ink">
            {formatXof(quote.total_xof)}
          </p>
          <p className="text-base font-medium text-ink">
            {quote.kind === "fixed" ? t("fixed") : t("visit")}
          </p>
          {quote.kind === "visit" && quote.visit_deductible ? (
            <p className="text-sm text-ink-muted">{t("deductible")}</p>
          ) : null}
        </div>

        <p className="flex items-start gap-2 text-base text-ink">
          <ClockIcon className="mt-0.5 size-5 shrink-0 text-ink-muted" />
          <span>
            <span className="font-medium">{slot.text}</span>
            <span className="text-ink-muted"> · {slot.range}</span>
          </span>
        </p>

        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h3 id={titleId} className="text-lg font-medium text-ink">
            {quote.provider.business_name}
          </h3>
          {quote.provider.verified ? (
            <span className="inline-flex items-center gap-1.5 text-sm font-medium text-success">
              <CheckIcon className="size-4" />
              {t("verified")}
            </span>
          ) : null}
          <RatingLine rating={quote.provider.rating} />
        </div>

        {quote.message.trim() ? (
          <blockquote className="border-l-2 border-line-strong pl-4 text-base leading-relaxed text-ink">
            {quote.message}
          </blockquote>
        ) : null}

        {quote.lines.length > 0 ? (
          <details className="group rounded-card border border-line">
            <summary className="flex min-h-12 cursor-pointer items-center px-4 text-base font-medium text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-strong">
              {t("lines")}
              <ChevronDownIcon className="ml-auto size-5 transition-transform group-open:rotate-180" />
            </summary>
            <ul className="flex flex-col gap-2 border-t border-line px-4 py-3">
              {quote.lines.map((line, index) => (
                <li key={index} className="flex justify-between gap-4 text-base text-ink">
                  <span>{readableLabel(line.label) || t(`line.${line.kind}`)}</span>
                  <span className="whitespace-nowrap">{formatXof(line.amount_xof)}</span>
                </li>
              ))}
            </ul>
          </details>
        ) : null}

        <p className="text-sm text-ink-muted">
          {t("validUntil", { date: formatDay(quote.valid_until, locale) })}
        </p>

        {children}
      </article>
    </li>
  );
}

function ConfirmStep({
  quote,
  now,
  pending,
  error,
  onConfirm,
  onBack,
}: {
  quote: ClientQuote;
  now: string;
  pending: boolean;
  error: RequestError | null;
  onConfirm: () => void;
  onBack: () => void;
}) {
  const t = useTranslations("requests");
  const slot = useSlotText(now)(quote.slot_start, quote.slot_end);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  return (
    <div className="flex flex-col gap-4 rounded-card border-2 border-ink bg-paper p-4">
      <h4 ref={heading} tabIndex={-1} className="text-lg font-medium text-ink outline-none">
        {t("quote.confirm.title")}
      </h4>
      <p className="text-base leading-relaxed text-ink">
        {t("quote.confirm.lead", {
          name: quote.provider.business_name,
          amount: formatXof(quote.total_xof),
          slot: `${slot.text}, ${slot.range}`,
        })}
      </p>
      {quote.kind === "visit" ? (
        <p className="text-base leading-relaxed text-ink">{t("quote.confirm.visitNote")}</p>
      ) : null}
      <p className="text-base leading-relaxed text-ink-muted">{t("quote.confirm.next")}</p>
      {error ? (
        <Alert
          tone="error"
          action={error.code === "quote_not_available" ? <RefreshButton /> : undefined}
        >
          {t(`errors.${error.key}`, error.values)}
        </Alert>
      ) : null}
      <div className="flex flex-col gap-3 sm:flex-row">
        <Button onClick={onConfirm} disabled={pending} aria-busy={pending}>
          {pending ? t("quote.confirm.sending") : t("quote.confirm.yes")}
        </Button>
        <Button variant="secondary" onClick={onBack} disabled={pending}>
          {t("quote.confirm.no")}
        </Button>
      </div>
    </div>
  );
}

export function QuotePicker({ quotes, now }: { quotes: ClientQuote[]; now: string }) {
  const t = useTranslations("requests.quote");
  const router = useRouter();
  const [, startRefresh] = useTransition();
  const [chosen, setChosen] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<RequestError | null>(null);
  const sorted = sortQuotes(quotes);

  async function accept(quote: ClientQuote) {
    setPending(true);
    setError(null);
    const result = await callAction(() => acceptQuoteAction(quote.public_id), refreshWebSession);
    if (result.ok) {
      // La page serveur se recharge : elle affiche l'attente du pro à la place des devis.
      startRefresh(() => router.refresh());
      return;
    }
    setPending(false);
    if (result.error.login) {
      window.location.assign(`/connexion?next=${encodeURIComponent(window.location.pathname)}`);
      return;
    }
    setError(result.error);
  }

  return (
    <ul className="flex flex-col gap-4">
      {sorted.map((quote) => (
        <QuoteCard
          key={quote.public_id}
          quote={quote}
          now={now}
          busy={pending && chosen === quote.public_id}
        >
          {chosen === quote.public_id ? (
            <ConfirmStep
              quote={quote}
              now={now}
              pending={pending}
              error={error}
              onConfirm={() => void accept(quote)}
              onBack={() => {
                setChosen(null);
                setError(null);
              }}
            />
          ) : (
            <Button
              disabled={pending}
              onClick={() => {
                setChosen(quote.public_id);
                setError(null);
              }}
              className="w-full sm:w-auto sm:self-start"
            >
              {t("choose")}
              <span className="sr-only">
                {" "}
                {t("forName", { name: quote.provider.business_name })}
              </span>
            </Button>
          )}
        </QuoteCard>
      ))}
    </ul>
  );
}
