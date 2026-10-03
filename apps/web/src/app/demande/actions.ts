"use server";

// Création d'une demande (spec 003, web 1). Le navigateur n'appelle jamais l'API lui-même : la
// Server Action passe par le BFF (cookies httpOnly, aucun jeton lisible) et le client généré.
// L'entrée vient du navigateur : elle est relue champ par champ, puis validée comme côté client.
import { meUpdate, requestsCreate } from "@jeflink/api-client";

import { coerceDraft, isIdempotencyKey } from "@/lib/requests/draft";
import { dakarToday } from "@/lib/requests/format";
import { buildRequestBody, hasErrors, isLocation, validateDraft } from "@/lib/requests/payload";
import type { ActionResult } from "@/lib/requests/result";
import { runAction } from "@/lib/requests/run-action";

export type CreatedRequest = { id: string; status: string };

export async function createRequestAction(input: {
  draft: unknown;
  location: unknown;
  idempotencyKey: unknown;
}): Promise<ActionResult<CreatedRequest>> {
  const draft = coerceDraft(input.draft);
  const key = input.idempotencyKey;
  const location = isLocation(input.location) ? input.location : null;
  const invalid = (code: string): ActionResult<CreatedRequest> => ({
    ok: false,
    error: {
      code,
      key: code,
      support: false,
      login: false,
      rotateKey: false,
    },
  });
  if (!isIdempotencyKey(key)) return invalid("idempotency_key_required");
  // Le nom n'est exigé que du profil incomplet ; l'API reste juge (`profile_incomplete`).
  const errors = validateDraft(draft, {
    hasLocation: location !== null,
    profileComplete: true,
    today: dakarToday(),
  });
  if (hasErrors(errors)) return invalid("invalid");

  return runAction(async (api) => {
    const name = draft.displayName.trim();
    if (name) await meUpdate({ display_name: name }, api.options);
    const response = await requestsCreate(buildRequestBody(draft, location), {
      ...api.options,
      headers: { "Idempotency-Key": key },
    });
    if (response.status !== 200 && response.status !== 201) throw new Error("réponse inattendue");
    return { id: response.data.public_id, status: response.data.status };
  });
}
