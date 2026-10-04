"use client";

// Fin de mission (spec 004, web 3). Question métier : « Le travail est fait : tout va bien, ou
// dois-je signaler un problème ? ». « Tout va bien » ne fait aucun appel : il propose l'avis (jamais
// exigé, la clôture n'en dépend pas). « Signaler un problème » ouvre le litige jusqu'à l'échéance.
import type { ClientReview } from "@jeflink/api-client";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button, ButtonLink } from "@/components/ui/button";
import { ChatIcon, StarIcon } from "@/components/ui/icons";
import { disputeWindowOpen } from "@/lib/bookings/dispute";

import { DisputeForm } from "./dispute-form";
import { ReviewForm } from "./review-form";

type Mode = "choice" | "review" | "dispute" | "saved";

export function FinishPanel({
  bookingId,
  status,
  canDispute,
  canReview,
  hasDispute,
  disputeDeadline,
  deadlineText,
  reviewUntilText,
  now,
  review,
  supportHref,
}: {
  bookingId: string;
  status: string;
  canDispute: boolean;
  canReview: boolean;
  hasDispute: boolean;
  disputeDeadline: string | null;
  deadlineText: string;
  reviewUntilText: string;
  now: string;
  review: ClientReview | null;
  supportHref: string | null;
}) {
  const t = useTranslations("bookings.finish");
  const tReview = useTranslations("bookings.review");
  const [mode, setMode] = useState<Mode>("choice");
  const windowOpen = canDispute && disputeWindowOpen(disputeDeadline, now);
  const completed = status === "completed";

  if (!review && !canReview && (!completed || hasDispute)) return null;

  return (
    <section
      aria-labelledby="finish-title"
      className="flex flex-col gap-4 rounded-card border border-line bg-surface p-5 sm:p-6"
    >
      <h2 id="finish-title" className="font-display text-2xl tracking-tight">
        {completed ? t("completedTitle") : t("reviewTitle")}
      </h2>

      {mode === "saved" ? <Alert tone="success">{tReview("saved")}</Alert> : null}

      {review && mode !== "review" ? (
        <div className="flex flex-col gap-3">
          <p className="flex items-center gap-2 text-lg font-medium text-ink">
            <StarIcon filled className="size-5 text-accent-strong" />
            {tReview("yours", { rating: review.rating })}
          </p>
          {review.tags.length > 0 ? (
            <ul className="flex flex-wrap gap-2">
              {review.tags.map((tag) => (
                <li
                  key={tag}
                  className="rounded-pill border border-line-strong px-3 py-1 text-sm text-ink"
                >
                  {tReview(`tags.${tag}`)}
                </li>
              ))}
            </ul>
          ) : null}
          {review.comment ? <p className="text-base text-ink">{review.comment}</p> : null}
          <p className="text-sm text-ink-muted">
            {review.published ? tReview("published") : tReview("pending")}
            {canReview ? ` ${tReview("editUntil", { when: reviewUntilText })}` : ""}
          </p>
          {canReview ? (
            <Button variant="secondary" className="self-start" onClick={() => setMode("review")}>
              {tReview("edit")}
            </Button>
          ) : null}
        </div>
      ) : null}

      {mode === "review" ? (
        <ReviewForm
          bookingId={bookingId}
          {...(review
            ? { initial: { rating: review.rating, tags: review.tags, comment: review.comment } }
            : {})}
          supportHref={supportHref}
          onSaved={() => setMode("saved")}
          onCancel={() => setMode("choice")}
        />
      ) : null}

      {mode === "dispute" ? (
        <DisputeForm
          bookingId={bookingId}
          deadlineText={deadlineText}
          supportHref={supportHref}
          onCancel={() => setMode("choice")}
        />
      ) : null}

      {(mode === "choice" || mode === "saved") && !review && canReview && !completed ? (
        <Button className="self-start" onClick={() => setMode("review")}>
          {t("giveReview")}
        </Button>
      ) : null}

      {(mode === "choice" || mode === "saved") && completed && !hasDispute ? (
        <>
          {!review && mode === "choice" ? <p className="text-lg text-ink">{t("lead")}</p> : null}
          <div className="flex flex-col gap-3 sm:flex-row">
            {!review && canReview ? (
              <Button onClick={() => setMode("review")}>{t("allGood")}</Button>
            ) : null}
            {windowOpen ? (
              <Button variant="secondary" onClick={() => setMode("dispute")}>
                {t("reportProblem")}
              </Button>
            ) : supportHref ? (
              <ButtonLink
                href={supportHref}
                target="_blank"
                rel="noopener noreferrer"
                variant="secondary"
              >
                <ChatIcon className="size-5" />
                {t("reportProblem")}
              </ButtonLink>
            ) : null}
          </div>
          {windowOpen ? (
            <p className="text-sm text-ink-muted">{t("until", { when: deadlineText })}</p>
          ) : (
            <p className="text-sm text-ink-muted">
              {supportHref ? t("windowClosed") : t("windowClosedNoSupport")}
            </p>
          )}
        </>
      ) : null}
    </section>
  );
}
