"use server";

// Actions du suivi d'une demande (spec 003, web 2) : accepter un devis, annuler une demande ou une
// réservation. Mêmes règles que la création : BFF, client généré, entrée du navigateur relue,
// jamais de `redirect` (le navigateur rafraîchit la page).
import { bookingsCancel, quotesAccept, requestsCancel } from "@jeflink/api-client";

import { isUuid } from "@/lib/requests/ids";
import type { ActionResult } from "@/lib/requests/result";
import { runAction } from "@/lib/requests/run-action";
import { validateCancel } from "@/lib/requests/status";

function invalid(code: string): ActionResult<{ id: string }> {
  return {
    ok: false,
    error: { code, key: code, support: false, login: false, rotateKey: false },
  };
}

/** Le client accepte un devis : la réservation naît (`accepted`), 200 au rejeu. */
export async function acceptQuoteAction(quoteId: unknown): Promise<ActionResult<{ id: string }>> {
  if (!isUuid(quoteId)) return invalid("not_found");
  return runAction(async (api) => {
    const response = await quotesAccept(quoteId, api.options);
    if (response.status !== 200 && response.status !== 201) throw new Error("réponse inattendue");
    return { id: quoteId };
  });
}

/** Annulation d'une demande ou d'une réservation, avec un motif de la liste fermée du client. */
export async function cancelAction(input: {
  kind: unknown;
  id: unknown;
  reason: unknown;
  note: unknown;
}): Promise<ActionResult<{ id: string }>> {
  const { kind, id } = input;
  const reason = typeof input.reason === "string" ? input.reason : "";
  const note = typeof input.note === "string" ? input.note.trim() : "";
  if ((kind !== "request" && kind !== "booking") || !isUuid(id)) return invalid("not_found");
  const problem = validateCancel(reason, note);
  if (problem === "reason") return invalid("reason_invalid");
  if (problem === "note") return invalid("note_invalid");
  const body = reason === "other" ? { reason, note } : { reason };
  return runAction(async (api) => {
    if (kind === "request") await requestsCancel(id, body, api.options);
    else await bookingsCancel(id, body, api.options);
    return { id };
  });
}
