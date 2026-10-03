// Résultat d'une Server Action de la demande (spec 003) : sérialisable, sans jeton. Une action ne
// redirige jamais (le formulaire serait perdu) : sur `needsRefresh`, le navigateur rafraîchit
// la session puis rejoue (spec 001, « Server Actions »).
import { type RequestError, describeRequestError } from "./errors.ts";

export type ActionResult<T> =
  { ok: true; data: T } | { ok: false; error: RequestError } | { needsRefresh: true };

export type SettledResult<T> = Exclude<ActionResult<T>, { needsRefresh: true }>;

const SESSION_ENDED: RequestError = {
  code: "not_authenticated",
  key: "not_authenticated",
  support: false,
  login: true,
  rotateKey: false,
};

/**
 * Appel d'une action depuis le navigateur : rafraîchit la session et rejoue UNE fois si le serveur
 * le demande ; une coupure du réseau devient une erreur `network`, jamais une exception.
 */
export async function callAction<T>(
  run: () => Promise<ActionResult<T>>,
  refresh: () => Promise<boolean>,
): Promise<SettledResult<T>> {
  try {
    let result = await run();
    if ("needsRefresh" in result) {
      if (!(await refresh())) return { ok: false, error: SESSION_ENDED };
      result = await run();
      if ("needsRefresh" in result) return { ok: false, error: SESSION_ENDED };
    }
    return result;
  } catch (error) {
    return { ok: false, error: describeRequestError(error, "network") };
  }
}
