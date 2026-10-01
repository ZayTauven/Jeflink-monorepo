// Cookies du BFF (spec 001, « BFF Next » ; S6, S10). Le navigateur ne voit jamais un jeton.

export const COOKIES = {
  /** Jeton d'accès : HttpOnly, Secure, SameSite=Lax, Path=/. */
  access: "__Host-jf_at",
  /** Refresh : SameSite=Strict, Path=/api/auth seulement (jamais élargi). */
  refresh: "__Secure-jf_rt",
  /** Jeton MFA entre l'OTP et le TOTP des Ops : 300 s, SameSite=Strict. */
  mfa: "__Host-jf_mfa",
  /** Identifiant d'appareil web, tient lieu d'install_id. */
  device: "__Host-jf_dev",
} as const;

export const REFRESH_PATH = "/api/auth";
const DEVICE_MAX_AGE = 400 * 24 * 3600;
const MFA_MAX_AGE = 300;

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

export function readCookies(request: Request): Map<string, string> {
  const jar = new Map<string, string>();
  for (const part of (request.headers.get("cookie") ?? "").split(";")) {
    const index = part.indexOf("=");
    if (index <= 0) continue;
    const name = part.slice(0, index).trim();
    try {
      jar.set(name, decodeURIComponent(part.slice(index + 1).trim()));
    } catch {
      // cookie mal encodé : ignoré
    }
  }
  return jar;
}

export function accessCookie(token: string, expiresAt: string): string {
  const seconds = (Date.parse(expiresAt) - Date.now()) / 1000;
  return serializeCookie(COOKIES.access, token, { maxAge: Number.isFinite(seconds) ? seconds : 0 });
}

export function refreshCookie(token: string, maxAge: number): string {
  return serializeCookie(COOKIES.refresh, token, {
    maxAge,
    path: REFRESH_PATH,
    sameSite: "Strict",
  });
}

export function mfaCookie(token: string): string {
  return serializeCookie(COOKIES.mfa, token, { maxAge: MFA_MAX_AGE, sameSite: "Strict" });
}

export function deviceCookie(id: string): string {
  return serializeCookie(COOKIES.device, id, { maxAge: DEVICE_MAX_AGE });
}

/** Efface la session (accès, refresh, MFA). L'identifiant d'appareil reste. */
export function clearSessionCookies(): string[] {
  return [
    serializeCookie(COOKIES.access, "", { maxAge: 0 }),
    serializeCookie(COOKIES.refresh, "", { maxAge: 0, path: REFRESH_PATH, sameSite: "Strict" }),
    serializeCookie(COOKIES.mfa, "", { maxAge: 0, sameSite: "Strict" }),
  ];
}
