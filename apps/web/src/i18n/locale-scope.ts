// Où la langue vient du cookie `NEXT_LOCALE` : l'espace client seulement (spec 001). Le site public
// est en français pour tous les visiteurs (ADR 0013) : son HTML ne varie pas d'un visiteur à
// l'autre, il pourra être mis en cache. Module pur, testé seul.
const COOKIE_PATHS = ["/compte", "/connexion", "/demande"];

/** Vrai pour les chemins de l'espace client ; `path` est celui posé par src/proxy.ts. */
export function usesLocaleCookie(path: string | null | undefined): boolean {
  if (!path) return false;
  const pathname = path.split(/[?#]/, 1)[0] ?? "";
  return COOKIE_PATHS.some((base) => pathname === base || pathname.startsWith(`${base}/`));
}
