// Cookies du BFF (spec 001, « BFF Next » ; S6, S10). Le navigateur ne voit jamais un jeton.

export const COOKIES = {
  /** Jeton d'accès : HttpOnly, Secure, SameSite=Lax, Path=/. */
  access: "__Host-jf_at",
  /** Refresh : SameSite=Strict, Path=/api/auth seulement (jamais élargi). */
  refresh: "__Secure-jf_rt",
  /**
   * Témoin de session, sans secret : même durée que le refresh, mais Path=/. Les pages (Server
   * Components) ne voient jamais le refresh ; ce témoin leur dit qu'un rafraîchissement est
   * possible quand l'accès a expiré.
   */
  session: "__Host-jf_sess",
  /** Jeton MFA entre l'OTP et le TOTP des Ops : 300 s, SameSite=Strict. */
  mfa: "__Host-jf_mfa",
  /** Identifiant d'appareil web (UUID), tient lieu d'install_id. */
  device: "__Host-jf_dev",
} as const;

export const REFRESH_PATH = "/api/auth";
const DEVICE_MAX_AGE = 400 * 24 * 3600;
const MFA_MAX_AGE = 300;
// Marge contre le décalage d'horloge entre le BFF et Django, et durée minimale du cookie d'accès.
const ACCESS_SKEW_SECONDS = 30;
const ACCESS_MIN_SECONDS = 60;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

type CookieOptions = { maxAge: number; path?: string; sameSite?: "Lax" | "Strict" };

export function serializeCookie(name: string, value: string, options: CookieOptions): string {
  const parts = [
    `${name}=${encodeURIComponent(value)}`,
    `Path=${options.path ?? "/"}`,
    `Max-Age=${Math.max(0, Math.floor(options.maxAge))}`,
    "HttpOnly",
    "Secure",
    `SameSite=${options.sameSite ?? "Lax"}`,
  ];
  return parts.join("; ");
}

export type CookieJar = {
  get(name: string): string | undefined;
  has(name: string): boolean;
  /** Plusieurs cookies de même nom (fixation par un sous-domaine, revue BFF M5). */
  duplicated(name: string): boolean;
};

export function readCookies(request: Request): CookieJar {
  const values = new Map<string, string[]>();
  for (const part of (request.headers.get("cookie") ?? "").split(";")) {
    const index = part.indexOf("=");
    if (index <= 0) continue;
    const name = part.slice(0, index).trim();
    try {
      const value = decodeURIComponent(part.slice(index + 1).trim());
      values.set(name, [...(values.get(name) ?? []), value]);
    } catch {
      // cookie mal encodé : ignoré
    }
  }
  return {
    get: (name) => {
      const found = values.get(name);
      return found && found.length === 1 ? found[0] : undefined;
    },
    has: (name) => (values.get(name)?.length ?? 0) === 1,
    duplicated: (name) => (values.get(name)?.length ?? 0) > 1,
  };
}

export function isDeviceId(value: string | undefined): value is string {
  return value !== undefined && UUID.test(value);
}

export function accessCookie(token: string, expiresAt: string): string {
  const seconds = (Date.parse(expiresAt) - Date.now()) / 1000 - ACCESS_SKEW_SECONDS;
  const maxAge = Number.isFinite(seconds)
    ? Math.max(ACCESS_MIN_SECONDS, seconds)
    : ACCESS_MIN_SECONDS;
  return serializeCookie(COOKIES.access, token, { maxAge });
}

/** Refresh (Path=/api/auth, Strict) et son témoin (Path=/), toujours posés ensemble. */
export function refreshCookies(token: string, maxAge: number): string[] {
  return [
    serializeCookie(COOKIES.refresh, token, { maxAge, path: REFRESH_PATH, sameSite: "Strict" }),
    serializeCookie(COOKIES.session, "1", { maxAge }),
  ];
}

export function mfaCookie(token: string): string {
  return serializeCookie(COOKIES.mfa, token, { maxAge: MFA_MAX_AGE, sameSite: "Strict" });
}

export function clearMfaCookie(): string {
  return serializeCookie(COOKIES.mfa, "", { maxAge: 0, sameSite: "Strict" });
}

export function deviceCookie(id: string): string {
  return serializeCookie(COOKIES.device, id, { maxAge: DEVICE_MAX_AGE });
}

/** Efface la session (accès, refresh, témoin, MFA). L'identifiant d'appareil reste. */
export function clearSessionCookies(): string[] {
  return [
    serializeCookie(COOKIES.access, "", { maxAge: 0 }),
    serializeCookie(COOKIES.refresh, "", { maxAge: 0, path: REFRESH_PATH, sameSite: "Strict" }),
    serializeCookie(COOKIES.session, "", { maxAge: 0 }),
    clearMfaCookie(),
  ];
}
