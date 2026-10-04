"use server";

// Actions du client sur sa réservation (spec 004, web 1 à 3) : no-show, code de fin, signalement
// d'une photo, avenant, litige, avis. Mêmes règles que `actions.ts` : BFF, client généré, entrée du
// navigateur relue avant tout appel, jamais de `redirect`. Chaque réponse de l'API est la
// réservation à jour ; la page se rafraîchit ensuite (rien d'autre n'est renvoyé au navigateur).
import {
  bookingsAmendmentsAccept,
  bookingsAmendmentsDecline,
  bookingsCompletionCodeRegenerate,
  bookingsCompletionCodeSms,
  bookingsNoShow,
  bookingsPhotosReport,
} from "@jeflink/api-client";

import { bookingError, describeBookingError } from "@/lib/bookings/errors";
import { isUuid } from "@/lib/requests/ids";
import type { ActionResult } from "@/lib/requests/result";
import { runAction } from "@/lib/requests/run-action";

type Done = { id: string };

function refuse(code: string): ActionResult<Done> {
  return { ok: false, error: bookingError(code) };
}

/** « Le pro n'est pas venu » : seulement après le créneau et la marge (l'API tranche). */
export async function noShowAction(bookingId: unknown): Promise<ActionResult<Done>> {
  if (!isUuid(bookingId)) return refuse("not_found");
  return runAction(async (api) => {
    const response = await bookingsNoShow(bookingId, api.options);
    if (response.status !== 200) throw new Error("réponse inattendue");
    return { id: bookingId };
  }, describeBookingError);
}

/** Nouveau code de fin (3 fois au plus). Le code lui-même ne passe jamais par ici : la page le relit. */
export async function regenerateCodeAction(bookingId: unknown): Promise<ActionResult<Done>> {
  if (!isUuid(bookingId)) return refuse("not_found");
  return runAction(async (api) => {
    const response = await bookingsCompletionCodeRegenerate(bookingId, api.options);
    if (response.status !== 200) throw new Error("réponse inattendue");
    return { id: bookingId };
  }, describeBookingError);
}

/** Envoi du code par SMS (2 de plus que l'envoi automatique, `429 sms_limit_reached` au-delà). */
export async function sendCodeSmsAction(bookingId: unknown): Promise<ActionResult<Done>> {
  if (!isUuid(bookingId)) return refuse("not_found");
  return runAction(async (api) => {
    const response = await bookingsCompletionCodeSms(bookingId, api.options);
    if (response.status !== 200) throw new Error("réponse inattendue");
    return { id: bookingId };
  }, describeBookingError);
}

/** « Signaler cette photo » : elle disparaît pour le client et le pro. */
export async function reportPhotoAction(
  bookingId: unknown,
  photoId: unknown,
): Promise<ActionResult<Done>> {
  if (!isUuid(bookingId) || !isUuid(photoId)) return refuse("not_found");
  return runAction(async (api) => {
    const response = await bookingsPhotosReport(bookingId, photoId, api.options);
    if (response.status !== 200) throw new Error("réponse inattendue");
    return { id: bookingId };
  }, describeBookingError);
}

/** Décision sur un avenant, depuis la session du client. Accepter envoie le prix vu, et `confirm` si la page a demandé confirmation. */
export async function amendmentAction(input: {
  bookingId: unknown;
  amendmentId: unknown;
  decision: unknown;
  /** Le prix que le client a vu : l'API refuse (`amendment_total_mismatch`) s'il a changé entre-temps. */
  total: unknown;
  /** Vrai après l'étape de confirmation de la page (hausse au-delà du seuil). */
  confirm: unknown;
}): Promise<ActionResult<Done>> {
  const { bookingId, amendmentId, decision, total } = input;
  if (!isUuid(bookingId) || !isUuid(amendmentId)) return refuse("not_found");
  if (decision !== "accept" && decision !== "decline") return refuse("invalid");
  if (decision === "accept" && !(typeof total === "number" && Number.isSafeInteger(total) && total > 0)) {
    return refuse("invalid");
  }
  const body = input.confirm === true ? { total_xof: total as number, confirm: true } : { total_xof: total as number };
  return runAction(async (api) => {
    const response =
      decision === "accept"
        ? await bookingsAmendmentsAccept(bookingId, amendmentId, body, api.options)
        : await bookingsAmendmentsDecline(bookingId, amendmentId, api.options);
    if (response.status !== 200) throw new Error("réponse inattendue");
    return { id: bookingId };
  }, describeBookingError);
}
