// Chemins du BFF (spec 001, S9 et S20) : proxy durci et paramètre `next` validé.

/** Préfixes jamais servis par le proxy générique (S9). `/api/auth/` a ses propres gestionnaires. */
export const DENIED_PREFIXES = ["/api/internal/", "/api/webhooks/", "/api/schema/", "/api/docs/"];

/**
 * Chemin d'API sûr à transmettre à Django, ou null. Le chemin reçu est déjà normalisé par
 * l'analyseur d'URL (segments `..` résolus) ; on refuse en plus toute trace d'encodage de point,
 * de barre ou d'antislash, les doubles barres et tout ce qui sort de `/api/`.
 */
export function safeApiPath(pathname: string): string | null {
  if (!pathname.startsWith("/api/")) return null;
  if (/%2e|%2f|%5c|\\|\/\/|\/\.\.?(\/|$)/i.test(pathname)) return null;
  if (DENIED_PREFIXES.some((prefix) => pathname.startsWith(prefix))) return null;
  return pathname;
}

/**
 * `next` d'une redirection : chemin relatif interne seulement (S20). Refuse les URL absolues,
 * `//hôte`, `/\hôte`, les schémas (`javascript:`) et les caractères de contrôle.
 */
export function safeNextPath(next: string | null | undefined, fallback = "/"): string {
  if (!next || next.length > 512) return fallback;
  // eslint-disable-next-line no-control-regex
  if (!next.startsWith("/") || next.startsWith("//") || /[\\\u0000-\u001f]/.test(next)) {
    return fallback;
  }
  try {
    const parsed = new URL(next, "https://bff.invalid");
    if (parsed.origin !== "https://bff.invalid") return fallback;
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return fallback;
  }
}
