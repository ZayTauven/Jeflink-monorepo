// Corps commun des Server Actions de la demande (spec 003). `server-only` : appelé depuis un
// fichier "use server" seulement.
import "server-only";

import type { BffServer } from "@jeflink/api-client/bff";

import { serverApi } from "../bff.ts";
import { describeRequestError } from "./errors.ts";
import type { ActionResult } from "./result.ts";

/**
 * Appel serveur d'une action : `{ needsRefresh: true }` si l'accès a expiré (jamais un
 * `redirect`), sinon la valeur ou l'erreur décrite (un code i18n, aucun message brut). Une
 * erreur qui n'est pas une réponse de l'API est une panne de notre côté, pas une coupure du
 * réseau du client.
 */
export async function runAction<T>(run: (api: BffServer) => Promise<T>): Promise<ActionResult<T>> {
  const api = await serverApi();
  if (api.needsRefresh) return { needsRefresh: true };
  try {
    return { ok: true, data: await run(api) };
  } catch (error) {
    return { ok: false, error: describeRequestError(error, "generic") };
  }
}
