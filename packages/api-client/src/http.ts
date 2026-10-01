// Seul point d'accès HTTP des fronts et apps Jeflink (règle 1 : aucun fetch à la main ailleurs).
// Chaque app le configure une fois au démarrage avec configureApiClient().
//
// Côté serveur Next (BFF, Server Components), la configuration est un singleton de module :
// elle ne porte JAMAIS de jeton. Le jeton passe à chaque appel (`accessToken`), et aucun refresh
// n'a lieu ici : le BFF redirige vers son route handler de refresh (spec 001, S4 ; ADR 0007).

export type ApiClientConfig = {
  /** Origine de l'API. Web/console : le BFF Next (même origine). Mobile : l'URL de l'API. */
  baseUrl: string;
  /** Mobile uniquement : jeton d'accès courant. Web/console : cookies httpOnly via le BFF. */
  getAccessToken?: () => string | null | Promise<string | null>;
  /** Langue envoyée en Accept-Language (fr par défaut, wo prévu). */
  getLanguage?: () => string;
  /**
   * Appelée sur un 401 d'une requête authentifiée par la configuration (pas par un jeton passé à
   * l'appel). Renvoie `true` si la session a été rafraîchie : la requête est alors rejouée une
   * seule fois avec le nouveau jeton. Un seul appel à la fois : les 401 simultanés attendent le
   * même rafraîchissement (le refresh tourne à chaque usage, deux en parallèle s'annuleraient).
   */
  onUnauthorized?: (error: ApiError) => Promise<boolean>;
};

/** Options d'un appel : celles de fetch, plus le jeton propre à l'appel (côté serveur). */
export type JeflinkRequestInit = RequestInit & {
  /** Jeton d'accès de CET appel, prioritaire sur la configuration. Jamais de refresh automatique. */
  accessToken?: string;
};

let config: ApiClientConfig = { baseUrl: "" };
let refreshing: Promise<boolean> | null = null;

export function configureApiClient(next: ApiClientConfig): void {
  config = next;
  refreshing = null;
}

/** Erreur API : `code` est le code métier stable renvoyé par Django (ex. "not_request_owner"). */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string | undefined;
  readonly body: unknown;

  constructor(status: number, body: unknown) {
    const code =
      typeof body === "object" && body !== null && "code" in body && typeof body.code === "string"
        ? body.code
        : undefined;
    super(code ?? `HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.body = body;
  }
}

/** Un seul rafraîchissement à la fois, partagé par tous les appels qui l'attendent. */
function refreshOnce(error: ApiError): Promise<boolean> {
  const handler = config.onUnauthorized;
  if (!handler) return Promise.resolve(false);
  if (!refreshing) {
    refreshing = handler(error)
      .catch(() => false)
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

async function send(url: string, options: JeflinkRequestInit): Promise<Response> {
  const { accessToken, ...init } = options;
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("Accept-Language", config.getLanguage?.() ?? "fr");
  // Exigé par le BFF (contrôle CSRF, spec 001 « BFF Next ») ; sans effet côté Django.
  headers.set("X-Requested-With", "jeflink");
  const token = accessToken ?? (await config.getAccessToken?.());
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const usesBearer = accessToken !== undefined || config.getAccessToken !== undefined;
  return fetch(`${config.baseUrl}${url}`, {
    ...init,
    headers,
    credentials: usesBearer ? "omit" : "include",
  });
}

async function readBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    // Page HTML d'un proxy (502, portail captif…) : on garde le texte brut.
    return text;
  }
}

/**
 * Mutateur orval. Les corps de requête doivent être rejouables (chaîne JSON, FormData, Blob) :
 * c'est le cas de tous les appels générés.
 */
export async function jeflinkFetch<T>(url: string, options: JeflinkRequestInit = {}): Promise<T> {
  let response = await send(url, options);
  let body = await readBody(response);
  if (response.status === 401 && options.accessToken === undefined && config.onUnauthorized) {
    const refreshed = await refreshOnce(new ApiError(401, body));
    if (refreshed) {
      response = await send(url, options); // un seul rejeu, jamais de boucle
      body = await readBody(response);
    }
  }
  if (!response.ok) throw new ApiError(response.status, body);
  return { data: body, status: response.status, headers: response.headers } as T;
}

// Lus par orval : type d'erreur des hooks générés et type des corps de requête.
export type ErrorType<_Error> = ApiError;
export type BodyType<BodyData> = BodyData;
