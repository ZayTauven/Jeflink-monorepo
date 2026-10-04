"use client";

// Avis sur la mission (spec 004, web 3). Question métier : « Comment s'est passée la mission ? ».
// Une note suffit : étoiles avec leur chiffre et un mot, puces avec libellé, commentaire facultatif.
// Les puces négatives n'apparaissent que sous 3 étoiles. Aucune icône seule.
import { useTranslations } from "next-intl";
import { type FormEvent, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Choice, Field, Fieldset, describedBy, inputClass } from "@/components/ui/form";
import { StarIcon } from "@/components/ui/icons";
import { COMMENT_MAX, RATINGS, sanitizeTags, tagsFor, validateReview } from "@/lib/bookings/review";

import { reviewAction } from "../finish-actions";
import { ActionError } from "./action-error";
import { useBookingAction } from "./use-booking-action";

export function ReviewForm({
  bookingId,
  initial,
  supportHref,
  onSaved,
  onCancel,
}: {
  bookingId: string;
  initial?: { rating: number; tags: readonly string[]; comment: string };
  supportHref: string | null;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const t = useTranslations("bookings.review");
  const uid = useId();
  const action = useBookingAction();
  const [rating, setRating] = useState(initial?.rating ?? 0);
  const [tags, setTags] = useState<string[]>(initial ? [...initial.tags] : []);
  const [comment, setComment] = useState(initial?.comment ?? "");
  const [problem, setProblem] = useState<"rating" | "comment" | null>(null);
  const commentId = `${uid}-comment`;

  function pickRating(value: number) {
    setRating(value);
    setTags((current) => sanitizeTags(value, current));
    setProblem(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (action.pending) return;
    const check = validateReview({ rating, tags, comment });
    if (!check.ok) {
      setProblem(check.problem === "comment" ? "comment" : "rating");
      return;
    }
    if (await action.run(() => reviewAction({ bookingId, ...check.value }))) onSaved();
  }

  return (
    <form
      onSubmit={submit}
      noValidate
      className="flex flex-col gap-5 rounded-card border border-line-strong p-4 sm:p-5"
    >
      <Fieldset
        id={`${uid}-rating`}
        legend={t("ratingLegend")}
        hint={t("ratingHint")}
        error={problem === "rating" ? t("ratingError") : undefined}
      >
        <div className="grid grid-cols-5 gap-2">
          {RATINGS.map((value) => (
            <label
              key={value}
              className={`flex min-h-12 cursor-pointer flex-col items-center justify-center gap-0.5 rounded-card border bg-surface px-1 py-2 text-base font-medium text-ink has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent-strong ${
                rating === value ? "border-2 border-ink bg-sand" : "border-line-strong"
              }`}
            >
              <input
                type="radio"
                name={`${uid}-rating`}
                value={value}
                checked={rating === value}
                onChange={() => pickRating(value)}
                className="sr-only"
              />
              <StarIcon filled={rating >= value} className="size-5 text-accent-strong" />
              <span>
                {value}
                <span className="sr-only"> {t("starsSr", { count: value })}</span>
              </span>
            </label>
          ))}
        </div>
        <p aria-live="polite" className="min-h-6 text-base font-medium text-ink">
          {rating > 0 ? t(`ratings.${rating}`) : ""}
        </p>
      </Fieldset>

      {rating > 0 ? (
        <Fieldset id={`${uid}-tags`} legend={t("tagsLegend")} hint={t("tagsHint")}>
          <div className="grid gap-2 sm:grid-cols-2">
            {tagsFor(rating).map((code) => (
              <Choice
                key={code}
                type="checkbox"
                checked={tags.includes(code)}
                onChange={(checked) =>
                  setTags((current) =>
                    checked ? [...current, code] : current.filter((tag) => tag !== code),
                  )
                }
              >
                {t(`tags.${code}`)}
              </Choice>
            ))}
          </div>
        </Fieldset>
      ) : null}

      <Field
        id={commentId}
        label={t("commentLabel")}
        hint={t("commentHint")}
        error={problem === "comment" ? t("commentError", { max: COMMENT_MAX }) : undefined}
      >
        <textarea
          id={commentId}
          rows={3}
          maxLength={COMMENT_MAX}
          value={comment}
          aria-invalid={problem === "comment" ? true : undefined}
          aria-describedby={describedBy(commentId, { hint: true, error: problem === "comment" })}
          onChange={(event) => {
            setComment(event.target.value);
            setProblem(null);
          }}
          className={inputClass}
        />
      </Field>

      {action.error ? <ActionError error={action.error} supportHref={supportHref} /> : null}

      <div className="flex flex-col gap-3 sm:flex-row">
        <Button type="submit" disabled={action.pending} aria-busy={action.pending}>
          {action.pending ? t("sending") : t("send")}
        </Button>
        <Button variant="secondary" onClick={onCancel} disabled={action.pending}>
          {t("cancel")}
        </Button>
      </div>
    </form>
  );
}
