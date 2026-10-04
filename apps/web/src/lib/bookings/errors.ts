// Erreurs des actions sur une réservation (spec 004, web 4) : chaque code de l'API a son libellé
// i18n (`bookings.errors.<code>`), testé contre `fr.json`. Même forme que `RequestError` (spec 003).
import type { RequestError } from "../requests/errors.ts";

const KNOWN = new Set([
  // 400
  "invalid",
  "idempotency_key_required",
  // 409
  "transition_not_allowed",
  "no_show_too_early",
  "no_show_contest_closed",
  "completion_code_locked",
  "completion_code_regen_limit",
  "photo_limit_reached",
  "idempotency_key_reused",
  "amendment_pending",
  "amendment_limit",
  "amendment_not_pending",
  "dispute_window_closed",
  "review_window_closed",
  "review_not_allowed",
  "provider_not_verified",
  "too_early",
  "amendment_total_mismatch",
  // 422
  "before_photos_required",
  "after_photos_required",
  "completion_code_invalid",
  "completion_proof_required",
  "no_code_reason_invalid",
  "occurred_at_invalid",
  "photo_invalid",
  "amendment_total_invalid",
  "amendment_confirmation_required",
  "amendment_reason_invalid",
  "note_invalid",
  "reason_invalid",
  "description_invalid",
  "review_invalid",
  "text_too_long",
  // 413, 429
  "photo_too_large",
  "sms_limit_reached",
  // Session absente, objet d'un autre compte
  "not_authenticated",
  "not_found",
]);

/** Impasses : le support WhatsApp est proposé avec le message. */
const WITH_SUPPORT = new Set([
  "completion_code_locked",
  "completion_code_regen_limit",
  "sms_limit_reached",
  "dispute_window_closed",
  "provider_not_verified",
  "generic",
]);

/** Liste exhaustive des codes connus (testée contre `fr.json`). */
export const BOOKING_ERROR_CODES: readonly string[] = [...KNOWN, "network", "generic"];

type ApiErrorLike = { name: string; status: number; code?: string | undefined };

function isApiError(error: unknown): error is ApiErrorLike {
  return (
    error instanceof Error &&
    error.name === "ApiError" &&
    typeof (error as Partial<ApiErrorLike>).status === "number"
  );
}

/** Erreur décrite pour un code connu (refus d'une entrée du navigateur, relue côté serveur). */
export function bookingError(code: string): RequestError {
  return {
    code,
    key: code,
    support: WITH_SUPPORT.has(code),
    login: code === "not_authenticated",
    rotateKey: false,
  };
}

/**
 * Même règle que `describeRequestError` : hors `ApiError`, `fallback` (navigateur : `network`,
 * serveur : `generic`). Un statut sans code lisible retombe sur un libellé proche, jamais sur un
 * message brut.
 */
export function describeBookingError(
  error: unknown,
  fallback: "network" | "generic" = "network",
): RequestError {
  if (!isApiError(error)) return bookingError(fallback);
  const code = error.code;
  if (code && KNOWN.has(code)) return bookingError(code);
  if (error.status === 401) return bookingError("not_authenticated");
  if (error.status === 404) return bookingError("not_found");
  if (error.status === 413) return bookingError("photo_too_large");
  return bookingError("generic");
}

/** La page est périmée (l'état a changé ailleurs) : proposer « Actualiser » avec l'erreur. */
const STALE = new Set([
  "transition_not_allowed",
  "amendment_not_pending",
  "amendment_total_mismatch",
  "completion_code_locked",
  "dispute_window_closed",
  "review_window_closed",
  "review_not_allowed",
  "no_show_too_early",
]);

export function isStale(code: string): boolean {
  return STALE.has(code);
}
