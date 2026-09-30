// Seul point d'accès HTTP des fronts et apps Jeflink (règle 1 : aucun fetch à la main ailleurs).
// Chaque app le configure une fois au démarrage avec configureApiClient().

export type ApiClientConfig = {
  /** Origine de l'API. Web/console : le BFF Next (même origine). Mobile : l'URL de l'API. */
  baseUrl: string;
  /** Mobile uniquement : jeton d'accès courant. Web/console : cookies httpOnly via le BFF. */
  getAccessToken?: () => string | null | Promise<string | null>;
  /** Langue envoyée en Accept-Language (fr par défaut, wo prévu). */
  getLanguage?: () => string;
};

let config: ApiClientConfig = { baseUrl: "" };

export function configureApiClient(next: ApiClientConfig): void {
  config = next;
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

export async function jeflinkFetch<T>(url: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  headers.set("Accept-Language", config.getLanguage?.() ?? "fr");
  const token = await config.getAccessToken?.();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${config.baseUrl}${url}`, {
    ...options,
    headers,
    credentials: config.getAccessToken ? "omit" : "include",
  });

  const text = await response.text();
  let body: unknown = undefined;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      // Page HTML d'un proxy (502, portail captif…) : on garde le texte brut.
      body = text;
    }
  }
  if (!response.ok) throw new ApiError(response.status, body);
  return { data: body, status: response.status, headers: response.headers } as T;
}

// Lus par orval : type d'erreur des hooks générés et type des corps de requête.
export type ErrorType<_Error> = ApiError;
export type BodyType<BodyData> = BodyData;
