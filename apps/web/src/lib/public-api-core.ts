// Accès public du BFF à l'API (spec 006, web 2 ; ADR 0013). Module pur (aucune dépendance à Next),
// testé seul ; `lib/public-api.ts` (server-only) l'assemble avec la configuration du BFF.
//
// Ce qu'un appel public ne porte JAMAIS : cookie, `Authorization`, `X-Jeflink-Client-Ip`,
// `X-Install-Id`, ni aucun en-tête du visiteur. Les en-têtes sont construits ici, de zéro, depuis
// une liste fermée : ceux que l'appelant passe (`init.headers`) sont ignorés. Rien ne lit
// `headers()` ni `cookies()` : le résultat est le même pour tous les visiteurs, donc partageable
// dans le cache de données de Next (une seule entrée).
import { hasUnsafePathSegments } from "@jeflink/api-client/paths";

/** Préfixes d'API autorisés, `GET` seulement. Tout autre chemin est refusé. */
export const PUBLIC_PREFIXES = ["/api/catalog/", "/api/zones/", "/api/stats/"] as const;

/** Étiquette du cache de données par préfixe (invalidation à la demande, `revalidateTag`). */
const TAG_BY_PREFIX: Readonly<Record<(typeof PUBLIC_PREFIXES)[number], PublicTag>> = {
  "/api/catalog/": "catalog",
  "/api/zones/": "zones",
  "/api/stats/": "stats",
};

export type PublicTag = "catalog" | "zones" | "stats";

/** Durée de validité d'une copie du cache de données : 5 minutes (spec 006). */
export const PUBLIC_REVALIDATE_SECONDS = 300;

/**
 * Liste exacte des en-têtes envoyés par `publicApi()` à Django. Rien d'autre ne part :
 * - `Accept` : JSON ;
 * - `Accept-Language` : `fr`, fixe (la langue vient de l'URL plus tard, jamais d'un cookie).
 * Pas de secret BFF : les endpoints publics sont `AllowAny`. Sans `X-Jeflink-Bff`, l'API prend
 * l'adresse du serveur Next comme appelant (`REMOTE_ADDR`) et applique `catalog_read` à ce seul
 * appelant ; avec le secret, elle exigerait `X-Jeflink-Client-Ip`, que ce module n'envoie jamais.
 */
export const PUBLIC_REQUEST_HEADERS = ["Accept", "Accept-Language"] as const;

export class PublicApiRefusal extends Error {
  constructor(reason: string) {
    super(`publicApi : ${reason}.`);
    this.name = "PublicApiRefusal";
  }
}

export type PublicApiSettings = {
  /** Origine interne de l'API (`JEFLINK_API_URL`). */
  apiUrl: string;
};

export type PublicRequest = {
  url: string;
  init: RequestInit & { next: { revalidate: number; tags: PublicTag[] } };
};

/** Chemin d'API autorisé et son étiquette de cache ; refus levé sinon. */
export function checkPublicPath(path: string): { path: string; search: string; tag: PublicTag } {
  if (hasUnsafePathSegments(path)) throw new PublicApiRefusal("chemin refusé");
  const target = new URL(path, "https://public.invalid");
  if (target.origin !== "https://public.invalid") throw new PublicApiRefusal("chemin refusé");
  const pathname = target.pathname;
  if (/%2e|%2f|%5c|\\|\/\/|\/\.\.?(\/|$)/i.test(pathname)) {
    throw new PublicApiRefusal("chemin refusé");
  }
  // Casse exacte : « /API/Catalog/ » n'est pas une route de Django, on ne la devine pas.
  const prefix = PUBLIC_PREFIXES.find((candidate) => pathname.startsWith(candidate));
  if (!prefix) throw new PublicApiRefusal("chemin hors liste");
  return { path: pathname, search: target.search, tag: TAG_BY_PREFIX[prefix] };
}

/** Requête vers Django : méthode `GET`, chemin autorisé, en-têtes de la liste fermée. */
export function buildPublicRequest(
  path: string,
  init: RequestInit,
  settings: PublicApiSettings,
): PublicRequest {
  if ((init.method ?? "GET").toUpperCase() !== "GET") {
    throw new PublicApiRefusal("seul GET est permis");
  }
  if (init.body !== undefined && init.body !== null) throw new PublicApiRefusal("GET sans corps");
  const { path: pathname, search, tag } = checkPublicPath(path);
  const headers = new Headers({
    Accept: "application/json",
    "Accept-Language": "fr",
  });
  return {
    url: `${settings.apiUrl}${pathname}${search}`,
    init: {
      method: "GET",
      headers,
      redirect: "manual",
      // Aucun cookie du navigateur ne passe par un fetch serveur ; `omit` le dit explicitement.
      credentials: "omit",
      ...(init.signal ? { signal: init.signal } : {}),
      next: { revalidate: PUBLIC_REVALIDATE_SECONDS, tags: [tag] },
    },
  };
}

type Copy = { body: string; status: number; contentType: string };

const MAX_COPIES = 500;

/**
 * Transport pour les fonctions générées de `@jeflink/api-client`. Dernière copie bonne servie si
 * l'API ne répond pas (réseau coupé, 5xx) : le site tient debout pendant une panne. Un 404 ou un
 * 4xx est une vraie réponse, jamais remplacé par une copie.
 */
export function createPublicTransport(
  settings: PublicApiSettings,
  deps: { fetchImpl?: typeof fetch; copies?: Map<string, Copy> } = {},
): (path: string, init: RequestInit) => Promise<Response> {
  const fetchImpl = deps.fetchImpl ?? fetch;
  const copies = deps.copies ?? new Map<string, Copy>();

  const serveCopy = (key: string): Response | null => {
    const copy = copies.get(key);
    if (!copy) return null;
    return new Response(copy.body, {
      status: copy.status,
      headers: { "Content-Type": copy.contentType, "X-Jeflink-Stale": "1" },
    });
  };

  return async (path, init) => {
    const request = buildPublicRequest(path, init, settings);
    let response: Response;
    try {
      response = await fetchImpl(request.url, request.init);
    } catch (error) {
      const stale = serveCopy(request.url);
      if (stale) return stale;
      throw error;
    }
    if (response.status >= 500) {
      const stale = serveCopy(request.url);
      if (stale) return stale;
      return response;
    }
    if (response.status === 200) {
      const body = await response.clone().text();
      copies.delete(request.url);
      copies.set(request.url, {
        body,
        status: 200,
        contentType: response.headers.get("content-type") ?? "application/json",
      });
      if (copies.size > MAX_COPIES) {
        const oldest = copies.keys().next().value;
        if (oldest !== undefined) copies.delete(oldest);
      }
    }
    return response;
  };
}

/** Codes d'API qui veulent dire « cette page n'existe pas » : les seuls qui donnent un 404. */
export const NOT_FOUND_CODES: ReadonlySet<string> = new Set(["trade_not_found", "zone_not_found"]);

/**
 * Vrai si l'erreur est une vraie absence (`404` avec un code d'absence). Une panne (réseau, 5xx,
 * 429…) n'est JAMAIS une absence : `notFound()` ferait désindexer la page (spec 006).
 */
export function isNotFoundError(error: unknown): boolean {
  if (!(error instanceof Error) || error.name !== "ApiError") return false;
  const { status, code } = error as Error & { status?: unknown; code?: unknown };
  return status === 404 && typeof code === "string" && NOT_FOUND_CODES.has(code);
}
