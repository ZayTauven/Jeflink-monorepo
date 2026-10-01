// Chemins du BFF (spec 001, S9 et S20) : proxy durci et paramètre `next` validé. Module sans
// dépendance serveur : la page de connexion (côté client) l'importe par `@jeflink/api-client/paths`.

/**
 * Verrou Web Locks du refresh, partagé par tous les onglets : la page de rebond du BFF et le
 * `onUnauthorized` du client web le prennent tous deux (le refresh tourne à chaque usage).
 */
export const REFRESH_LOCK = "jf-refresh";

/**
 * Clé localStorage de la date du dernier refresh réussi (aucun secret) : un onglet qui obtient le
 * verrou juste après un refresh réussi ailleurs ne le refait pas (page de rebond et client web).
 */
export const REFRESHED_AT_KEY = "jf-refreshed-at";

/** Seul endpoint du refresh web : `POST` le fait, `GET` renvoie la page de rebond. */
export const REFRESH_ENDPOINT = "/api/auth/token/refresh/";

/**
 * Vrai si le chemin BRUT (avant toute normalisation par `new URL` ou `fetch`) contient un segment
 * `.` ou `..`, un point, une barre ou un antislash encodés, un antislash ou une double barre. Un
 * paramètre de route piégé (`..%2F..%2Fme%2F…`) ne peut alors jamais changer d'endpoint
 * (revue BFF, I-C). La requête (`?…`) et le fragment ne sont pas contrôlés.
 */
export function hasUnsafePathSegments(url: string): boolean {
  const path = url.split(/[?#]/, 1)[0] ?? "";
  return /%2e|%2f|%5c|\\|\/\//i.test(path) || /(^|\/)\.\.?(\/|$)/.test(path);
}

/** Préfixes jamais servis par le proxy générique (S9). `/api/auth/` a ses propres gestionnaires. */
export const DENIED_PREFIXES = ["/api/internal/", "/api/webhooks/", "/api/schema/", "/api/docs/"];

/**
 * Chemin d'API sûr à transmettre à Django, ou null. Le chemin reçu est déjà normalisé par
 * l'analyseur d'URL (segments `..` résolus) ; on refuse en plus toute trace d'encodage de point,
 * de barre ou d'antislash, les doubles barres et tout ce qui sort de `/api/`. Les préfixes
 * interdits sont comparés en minuscules et avec une barre finale.
 */
export function safeApiPath(pathname: string): string | null {
  if (!pathname.startsWith("/api/")) return null;
  if (/%2e|%2f|%5c|\\|\/\/|\/\.\.?(\/|$)/i.test(pathname)) return null;
  const compared = `${pathname.toLowerCase().replace(/\/+$/, "")}/`;
  if (DENIED_PREFIXES.some((prefix) => compared.startsWith(prefix))) return null;
  return pathname;
}

/**
 * `next` d'une redirection : chemin relatif interne seulement (S20). Le résultat est contrôlé
 * APRÈS normalisation (`/.//hôte`, `/a/..//hôte` deviennent `//hôte` : refusés), jamais sous
 * `/api/` (pas de chaîne de redirections), sans schéma ni caractère de contrôle.
 */
export function safeNextPath(next: string | null | undefined, fallback = "/"): string {
  if (!next || next.length > 512) return fallback;
  // eslint-disable-next-line no-control-regex
  if (!next.startsWith("/") || /[\\\u0000-\u001f\u007f]/.test(next)) return fallback;
  let normalized: string;
  try {
    const parsed = new URL(next, "https://bff.invalid");
    if (parsed.origin !== "https://bff.invalid") return fallback;
    normalized = `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return fallback;
  }
  if (
    !normalized.startsWith("/") ||
    normalized.startsWith("//") ||
    normalized.startsWith("/\\") ||
    /^\/api(\/|$|\?|#)/i.test(normalized)
  ) {
    return fallback;
  }
  // `/%61pi/…` est `/api/…` pour le serveur : contrôle aussi sur la forme décodée (revue BFF, m6).
  try {
    if (/^\/api(\/|$)/i.test(decodeURIComponent(normalized.split(/[?#]/, 1)[0] ?? ""))) {
      return fallback;
    }
  } catch {
    return fallback;
  }
  return normalized;
}
