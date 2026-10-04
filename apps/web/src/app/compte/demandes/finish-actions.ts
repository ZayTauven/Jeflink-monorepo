"use server";

// Actions de fin de mission (spec 004, web 3) : litige et avis. Mêmes règles que
// `booking-actions.ts` : BFF, client généré, entrée du navigateur relue, jamais de `redirect`.
import { bookingsDispute, bookingsReviewPut } from "@jeflink/api-client";

import { validateDispute } from "@/lib/bookings/dispute";
import { bookingError, describeBookingError } from "@/lib/bookings/errors";
import { validateReview } from "@/lib/bookings/review";
import { isUuid } from "@/lib/requests/ids";
import type { ActionResult } from "@/lib/requests/result";
import { runAction } from "@/lib/requests/run-action";

type Done = { id: string };

function refuse(code: string): ActionResult<Done> {
  return { ok: false, error: bookingError(code) };
}

/** Litige jusqu'à l'échéance : motif de la liste fermée, texte de 10 à 1 000 caractères. */
export async function disputeAction(input: {
  bookingId: unknown;
  reason: unknown;
  description: unknown;
}): Promise<ActionResult<Done>> {
  const { bookingId } = input;
  const reason = typeof input.reason === "string" ? input.reason : "";
  const description = typeof input.description === "string" ? input.description.trim() : "";
  if (!isUuid(bookingId)) return refuse("not_found");
  const problem = validateDispute(reason, description);
  if (problem === "reason") return refuse("reason_invalid");
  if (problem === "description") return refuse("description_invalid");
  return runAction(async (api) => {
    const response = await bookingsDispute(bookingId, { reason, description }, api.options);
    if (response.status !== 200) throw new Error("réponse inattendue");
    return { id: bookingId };
  }, describeBookingError);
}

/** Avis : une note suffit ; puces et commentaire facultatifs. Créé ou modifié (un par réservation). */
export async function reviewAction(input: {
  bookingId: unknown;
  rating: unknown;
  tags: unknown;
  comment: unknown;
}): Promise<ActionResult<Done>> {
  const { bookingId } = input;
  if (!isUuid(bookingId)) return refuse("not_found");
  const check = validateReview(input);
  if (!check.ok) return refuse(check.problem === "comment" ? "text_too_long" : "review_invalid");
  const { rating, tags, comment } = check.value;
  return runAction(async (api) => {
    const response = await bookingsReviewPut(
      bookingId,
      comment ? { rating, tags, comment } : { rating, tags },
      api.options,
    );
    if (response.status !== 200) throw new Error("réponse inattendue");
    return { id: bookingId };
  }, describeBookingError);
}
