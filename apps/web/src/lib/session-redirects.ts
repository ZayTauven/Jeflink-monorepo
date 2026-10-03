// Décisions de redirection côté serveur (spec 001, « BFF Next », S6). Module pur, testé seul ;
// `lib/bff.ts` les applique avec `redirect()`.
import { LOGIN_PATH } from "./routes.ts";

type SessionState = { needsRefresh: boolean; refreshPath: (next: string) => string };

/** Vrai sur la page de connexion elle-même : jamais de redirection vers elle-même (boucle). */
export function isLoginPath(path: string): boolean {
  const rest = path.slice(LOGIN_PATH.length);
  return path.startsWith(LOGIN_PATH) && (rest === "" || /^[/?#]/.test(rest));
}

function loginPath(next: string): string {
  return `${LOGIN_PATH}?next=${encodeURIComponent(next)}`;
}

/** Page qui exige une session : rebond de refresh si l'accès a expiré, sinon rien. */
export function sessionRedirect(api: SessionState, path: string): string | null {
  return api.needsRefresh ? api.refreshPath(path) : null;
}

function isUnauthorized(error: unknown): boolean {
  return (
    error instanceof Error &&
    error.name === "ApiError" &&
    (error as Error & { status?: unknown }).status === 401
  );
}

/**
 * Cible d'une erreur d'appel serveur, ou null pour relancer l'erreur.
 * - autre chose qu'un 401 : relancée ;
 * - sur la page de connexion : relancée (pas de boucle) ;
 * - accès expiré mais refresh possible : rebond de refresh (pas d'OTP ni de SMS pour rien) ;
 * - accès présent mais refusé (session révoquée, compte désactivé) : connexion, jamais le
 *   refresh, qui bouclerait.
 */
export function unauthorizedRedirect(
  error: unknown,
  api: SessionState,
  path: string,
): string | null {
  if (!isUnauthorized(error) || isLoginPath(path)) return null;
  return api.needsRefresh ? api.refreshPath(path) : loginPath(path);
}
