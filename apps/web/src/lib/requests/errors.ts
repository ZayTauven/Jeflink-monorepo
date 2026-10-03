// Erreurs du parcours demande, devis, réservation (spec 003, web 1 et 2) : chaque code de l'API a
// son libellé i18n (`requests.errors.<clé>`). Le résultat est sérialisable : une Server Action le
// renvoie tel quel au navigateur.

export type Candidate = { slug: string; name: string };

export type RequestError = {
  /** Code de l'API, ou `network`, `generic`. */
  code: string;
  /** Clé sous `requests.errors` : le code, ou sa variante `_wait`. */
  key: string;
  values?: Record<string, number>;
  /** Proposer le lien WhatsApp du support (aucune impasse). */
  support: boolean;
  /** `zone_ambiguous` : les quartiers entre lesquels choisir. */
  candidates?: Candidate[];
  /** `invalid` : champs refusés, quand l'API les nomme. */
  fields?: string[];
  /** Session absente : renvoyer à la connexion. */
  login: boolean;
  /** La clé d'idempotence ne vaut plus : en prendre une neuve avant un nouvel essai. */
  rotateKey: boolean;
};

const KNOWN = new Set([
  "invalid",
  "idempotency_key_required",
  "not_authenticated",
  "profile_incomplete",
  "role_required",
  "not_found",
  "request_limit_reached",
  "idempotency_key_reused",
  "request_closed",
  "quote_not_available",
  "transition_not_allowed",
  "zone_ambiguous",
  "trade_not_in_zone",
  "out_of_area",
  "trade_not_found",
  "trade_inactive",
  "zone_not_found",
  "zone_inactive",
  "zone_required",
  "service_not_in_trade",
  "landmark_or_location_required",
  "description_required",
  "slot_invalid",
  "reason_invalid",
  "note_invalid",
  "text_too_long",
  "location_invalid",
  "request_rate_limited",
  "rate_limit_unavailable",
  // Profil : nom refusé au moment d'envoyer la demande.
  "display_name_length",
  "display_name_invalid",
  "display_name_reserved",
]);

/** Codes qui ne se résolvent pas seuls : le support WhatsApp est proposé. */
const WITH_SUPPORT = new Set([
  "trade_not_in_zone",
  "out_of_area",
  "trade_inactive",
  "trade_not_found",
  "zone_not_found",
  "zone_inactive",
  "rate_limit_unavailable",
  "role_required",
  "generic",
]);

/** Liste exhaustive des codes connus (testée contre `fr.json`). */
export const REQUEST_ERROR_CODES: readonly string[] = [...KNOWN, "network", "generic"];

type ApiErrorLike = { name: string; status: number; code?: string | undefined; body: unknown };

function isApiError(error: unknown): error is ApiErrorLike {
  return (
    error instanceof Error &&
    error.name === "ApiError" &&
    typeof (error as Partial<ApiErrorLike>).status === "number"
  );
}

function field(body: unknown, name: string): unknown {
  return typeof body === "object" && body !== null
    ? (body as Record<string, unknown>)[name]
    : undefined;
}

/** `candidates[{slug,name}]` d'un 422 `zone_ambiguous`, ou `[]` si la forme n'est pas la bonne. */
export function candidatesFrom(body: unknown): Candidate[] {
  const raw = field(body, "candidates");
  if (!Array.isArray(raw)) return [];
  const out: Candidate[] = [];
  for (const item of raw) {
    const slug = field(item, "slug");
    const name = field(item, "name");
    if (typeof slug === "string" && slug && typeof name === "string" && name) {
      out.push({ slug, name });
    }
  }
  return out;
}

function fieldNames(body: unknown): string[] {
  const raw = field(body, "fields");
  if (Array.isArray(raw)) return raw.filter((item): item is string => typeof item === "string");
  if (typeof raw === "object" && raw !== null) return Object.keys(raw);
  return [];
}

function make(code: string, extra: Partial<RequestError> = {}): RequestError {
  return {
    code,
    key: code,
    support: WITH_SUPPORT.has(code),
    login: code === "not_authenticated",
    rotateKey: code === "idempotency_key_reused",
    ...extra,
  };
}

/**
 * `fallback` : ce que veut dire une erreur qui n'est pas une `ApiError`. Dans le navigateur, une
 * coupure (`network` : jamais confondue avec un refus, la saisie reste) ; sur le serveur, une
 * panne de notre côté (`generic`).
 */
export function describeRequestError(
  error: unknown,
  fallback: "network" | "generic" = "network",
): RequestError {
  if (!isApiError(error)) return make(fallback);
  const code = error.code;
  if (code === "zone_ambiguous") {
    const candidates = candidatesFrom(error.body);
    // Sans candidats lisibles, on ne peut pas faire choisir : repli sur le support.
    return candidates.length ? make(code, { candidates }) : make("generic");
  }
  if (code === "request_rate_limited") {
    const seconds = field(error.body, "retry_after");
    if (typeof seconds === "number" && Number.isFinite(seconds) && seconds > 0) {
      return make(code, {
        key: `${code}_wait`,
        values: { minutes: Math.max(1, Math.ceil(seconds / 60)) },
      });
    }
    return make(code);
  }
  if (code === "invalid") {
    const fields = fieldNames(error.body);
    return make(code, fields.length ? { fields } : {});
  }
  // Échec de création côté serveur : même message que toute panne de notre côté.
  if (code === "request_create_failed") return make("generic");
  if (code && KNOWN.has(code)) return make(code);
  if (error.status === 401) return make("not_authenticated");
  if (error.status === 429) return make("request_rate_limited");
  return make("generic");
}
