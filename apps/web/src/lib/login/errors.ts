// Erreurs du parcours de connexion (spec 001, « Aucune impasse », T3) : chaque code de l'API a
// son libellé i18n (`connexion.errors.<clé>`) ; une coupure réseau se distingue d'un code faux.

export type LoginError = {
  /** Code d'erreur (celui de l'API, ou `network`, `generic`). */
  code: string;
  /** Clé sous `connexion.errors` : le code, ou sa variante `_wait`, `_remaining`. */
  key: string;
  values?: Record<string, number>;
  /** Proposer le lien WhatsApp du support (message pré-rempli, sans code ni numéro). */
  support: boolean;
  /** Le challenge est mort : retour à l'étape téléphone. */
  restart: boolean;
  /** Numéro hors régions couvertes : écran dédié, pas une erreur en ligne. */
  region: boolean;
};

const KNOWN = new Set([
  "phone_invalid",
  "phone_not_mobile",
  "otp_rate_limited",
  "otp_temporarily_unavailable",
  "otp_request_in_progress",
  "client_challenge_failed",
  "otp_resend_too_early",
  "otp_resend_exhausted",
  "otp_challenge_invalid",
  "otp_invalid",
  "otp_expired",
  "otp_locked",
  "otp_already_used",
  "terms_not_accepted",
  "account_disabled",
  "account_not_allowed",
  "fresh_start_not_allowed",
  "reauth_required",
  "account_deletion_blocked",
  "display_name_length",
  "display_name_invalid",
  "display_name_reserved",
]);
const WITH_SUPPORT = new Set([
  "otp_rate_limited",
  "otp_temporarily_unavailable",
  "otp_resend_exhausted",
  "otp_locked",
  "account_disabled",
  "account_not_allowed",
  "fresh_start_not_allowed",
  "account_deletion_blocked",
  "generic",
]);
const RESTART = new Set([
  "otp_challenge_invalid",
  "otp_locked",
  "otp_resend_exhausted",
  "otp_already_used",
  "reauth_required",
]);

type ApiErrorLike = { name: string; status: number; code?: string | undefined; body: unknown };

function isApiError(error: unknown): error is ApiErrorLike {
  return (
    error instanceof Error &&
    error.name === "ApiError" &&
    typeof (error as Partial<ApiErrorLike>).status === "number"
  );
}

function numberField(body: unknown, name: string): number | undefined {
  if (typeof body !== "object" || body === null) return undefined;
  const value = (body as Record<string, unknown>)[name];
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : undefined;
}

function make(code: string, variant?: string, values?: Record<string, number>): LoginError {
  return {
    code,
    key: variant ? `${code}_${variant}` : code,
    ...(values ? { values } : {}),
    support: WITH_SUPPORT.has(code),
    restart: RESTART.has(code),
    region: false,
  };
}

export function describeLoginError(error: unknown): LoginError {
  // fetch rejeté (hors ligne, coupure) : jamais confondu avec un code faux ; la saisie reste.
  if (!isApiError(error)) return make("network");
  const code = error.code;
  if (code === "phone_region_not_supported") return { ...make(code), region: true };
  if (code === "invalid") return make("phone_invalid"); // validation de format
  if (code === "otp_rate_limited" || code === "otp_resend_too_early") {
    const seconds = numberField(error.body, "retry_after");
    if (seconds !== undefined) {
      return make(code, "wait", { minutes: Math.max(1, Math.ceil(seconds / 60)), seconds });
    }
  }
  if (code === "otp_invalid") {
    const remaining = numberField(error.body, "attempts_remaining");
    if (remaining !== undefined) return make(code, "remaining", { remaining });
  }
  if (code && KNOWN.has(code)) return make(code);
  if (error.status === 429) return make("otp_rate_limited");
  return make("generic");
}
