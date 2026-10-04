// Avis (spec 004, web 3) : une note suffit, les puces et le commentaire sont facultatifs. Les
// puces négatives ne sont permises que sous 3 étoiles ; les positives, toujours.

export const POSITIVE_TAGS = ["on_time", "quality", "clean", "price_kept"] as const;
export const NEGATIVE_TAGS = ["late", "redo_needed", "messy", "price_changed"] as const;
export const COMMENT_MAX = 500;
export const RATINGS = [1, 2, 3, 4, 5] as const;

const NEGATIVE_BELOW = 3;

export function isRating(value: unknown): value is (typeof RATINGS)[number] {
  return typeof value === "number" && Number.isInteger(value) && value >= 1 && value <= 5;
}

/** Puces proposées pour une note : négatives seulement sous 3 étoiles. */
export function tagsFor(rating: number): readonly string[] {
  if (rating >= 1 && rating < NEGATIVE_BELOW) return [...POSITIVE_TAGS, ...NEGATIVE_TAGS];
  return POSITIVE_TAGS;
}

/** Retire les puces qui ne vont plus avec la note (la note change, des puces tombent). */
export function sanitizeTags(rating: number, tags: readonly string[]): string[] {
  const allowed = tagsFor(rating);
  return [...new Set(tags)].filter((tag) => allowed.includes(tag));
}

export type ReviewInput = { rating: unknown; tags?: unknown; comment?: unknown };
export type ReviewCheck =
  | { ok: true; value: { rating: number; tags: string[]; comment: string } }
  | { ok: false; problem: "rating" | "tags" | "comment" };

/** Une note de 1 à 5 suffit ; puces de la liste permise ; commentaire de 500 caractères au plus. */
export function validateReview(input: ReviewInput): ReviewCheck {
  if (!isRating(input.rating)) return { ok: false, problem: "rating" };
  const rawTags = Array.isArray(input.tags) ? (input.tags as unknown[]) : [];
  if (!rawTags.every((tag): tag is string => typeof tag === "string")) {
    return { ok: false, problem: "tags" };
  }
  const tags = sanitizeTags(input.rating, rawTags);
  if (tags.length !== new Set(rawTags).size) return { ok: false, problem: "tags" };
  const comment = typeof input.comment === "string" ? input.comment.trim() : "";
  if (comment.length > COMMENT_MAX) return { ok: false, problem: "comment" };
  return { ok: true, value: { rating: input.rating, tags, comment } };
}

/** « 4,8 » : une décimale, virgule française. */
export function formatAverage(average: number): string {
  return (Math.round(average * 10) / 10).toFixed(1).replace(".", ",");
}
