// Seul point d'accès HTTP des fronts et apps Jeflink (règle 1 : aucun fetch à la main ailleurs).
// Chaque app le configure une fois au démarrage avec configureApiClient().
//
// Côté serveur Next (Server Components, actions), la configuration est un singleton de module :
// elle ne porte JAMAIS de jeton. Un appel serveur passe un `transport`, fourni par le BFF
// (`bff.server(request)`) : il porte le jeton et le secret de CETTE requête dans une fermeture,
// et l'appel ne consulte alors rien du singleton, ni jeton, ni refresh, ni langue
// (spec 001, S4 ; ADR 0007).

export type ApiClientConfig = {
  /** Origine de l'API. Web/console : le BFF Next (même origine). Mobile : l'URL de l'API. */
  baseUrl: string;
  /** Mobile uniquement : jeton d'accès courant. Web/console : cookies httpOnly via le BFF. */
  getAccessToken?: () => string | null | Promise<string | null>;
  /** Langue envoyée en Accept-Language (fr par défaut, wo prévu). */
  getLanguage?: () => string;
  /**
   * Appelée sur un 401 d'une requête authentifiée par la configuration. Renvoie `true` si la
   * session a été rafraîchie : la requête est alors rejouée une seule fois. Un seul appel à la
   * fois : les 401 simultanés attendent le même rafraîchissement (le refresh tourne à chaque
   * usage, deux en parallèle s'annuleraient).
   */
  onUnauthorized?: (error: ApiError) => Promise<boolean>;
};

/** Envoi d'un appel serveur vers Django : chemin d'API (`/api/...`) et options fetch. */
export type Transport = (path: string, init: RequestInit) => Promise<Response>;

/** Options d'un appel : celles de fetch, plus le transport serveur éventuel. */
export type JeflinkRequestInit = RequestInit & {
  /**
   * Présent = appel serveur : jamais le jeton ni le refresh de la configuration. Une fonction ne
   * se sérialise pas : passée par erreur à un Client Component, elle ne fuit rien.
   */
  transport?: Transport;
};

let config: ApiClientConfig = { baseUrl: "" };
let refreshing: Promise<boolean> | null = null;
// Change à chaque reconfiguration et à chaque fin de session : une requête partie sous un compte
// n'est jamais rejouée sous un autre après un rafraîchissement.
let generation = 0;

export function configureApiClient(next: ApiClientConfig): void {
  config = next;
  refreshing = null;
  generation += 1;
}

/** À appeler à la déconnexion ou au changement d'utilisateur (apps mobiles, Provider web). */
export function resetApiClientSession(): void {
  refreshing = null;
  generation += 1;
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
function refreshOnce(handler: NonNullable<ApiClientConfig["onUnauthorized"]>, error: ApiError) {
  if (!refreshing) {
    const pending: Promise<boolean> = handler(error)
      .catch(() => false)
      .finally(() => {
        // Ne remet à zéro que SA promesse : jamais celle d'un refresh lancé depuis.
        if (refreshing === pending) refreshing = null;
      });
    refreshing = pending;
  }
  return refreshing;
}

async function send(url: string, options: JeflinkRequestInit): Promise<Response> {
  const { transport, ...init } = options;
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  // Exigé par le BFF (contrôle CSRF, spec 001 « BFF Next ») ; sans effet côté Django.
  headers.set("X-Requested-With", "jeflink");
  if (transport) {
    // Appel serveur : la langue et le jeton viennent de la requête entrante, via le transport.
    return transport(url, { ...init, headers });
  }
  if (!headers.has("Accept-Language"))
    headers.set("Accept-Language", config.getLanguage?.() ?? "fr");
  const token = await config.getAccessToken?.();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(`${config.baseUrl}${url}`, {
    ...init,
    headers,
    credentials: config.getAccessToken !== undefined ? "omit" : "include",
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
  const startedUnder = generation;
  let response = await send(url, options);
  let body = await readBody(response);
  const handler = config.onUnauthorized;
  if (response.status === 401 && !options.transport && handler) {
    const refreshed = await refreshOnce(handler, new ApiError(401, body));
    // Pas de rejeu si la session a changé entre-temps (déconnexion, autre compte).
    if (refreshed && generation === startedUnder) {
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
