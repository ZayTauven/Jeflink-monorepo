// BFF Next de Jeflink (spec 001, « BFF Next » ; ADR 0007 ; S4, S6, S9, S10, S20).
//
// Un seul point d'entrée, `handle(request)`, monté derrière la route attrape-tout de l'app
// (`app/api/[...path]/route.ts`, runtime nodejs) : les endpoints qui émettent des jetons ont leurs
// gestionnaires, tout le reste passe par le proxy durci. Aucun état de module : la configuration
// est figée par `createBff`, et chaque requête porte ses propres cookies et en-têtes.
//
// Côté serveur (Server Components, actions), `server(request)` fournit un transport fermé : le
// jeton et le secret restent dans une fermeture, jamais dans un objet lisible ou sérialisable.

import { isIP } from "node:net";

import type { Transport } from "../http.ts";
import {
  COOKIES,
  type CookieJar,
  accessCookie,
  clearMfaCookie,
  clearSessionCookies,
  deviceCookie,
  isDeviceId,
  mfaCookie,
  readCookies,
  refreshCookies,
  serializeCookie,
} from "./cookies.ts";
import {
  REFRESHED_AT_KEY,
  REFRESH_ENDPOINT,
  REFRESH_LOCK,
  hasUnsafePathSegments,
  safeApiPath,
  safeNextPath,
} from "./paths.ts";

export type BffConfig = {
  /** Contexte imposé à Django : jamais choisi par le navigateur (S10). */
  app: "web" | "console";
  /** API Django sur le réseau interne, par son hôte interne (ex. https://api). */
  apiUrl: string;
  /** Origines exactes autorisées pour toute requête non GET (CSRF). */
  allowedOrigins: string[];
  /** Secret partagé avec Django (BFF_SHARED_SECRETS), jamais en NEXT_PUBLIC_. */
  bffSecret: string;
  /**
   * IP cliente lue depuis UNE source fiable de l'hébergeur ; jamais X-Forwarded-For brut. Une
   * valeur qui n'est pas une adresse IP est ignorée.
   */
  clientIp: (headers: Headers) => string | null;
  /** Durée du cookie de refresh : 30 j (web), 12 h (console). */
  refreshMaxAgeSeconds: number;
  /** Page de connexion (chemin interne, sans requête), cible d'un refresh impossible. */
  loginPath: string;
  /**
   * Domaine parent (ex. `jeflink.sn`) : un refresh en double planté par un sous-domaine avec ce
   * `Domain` est aussi effacé (revue BFF, m1). Sans lui, seul le cookie hôte est effacé.
   */
  cookieDomain?: string;
  /** Alerte de sécurité, sans aucune valeur de jeton. Par défaut : une ligne JSON sur stderr. */
  onSecurityEvent?: (event: BffSecurityEvent) => void;
};

/** Événement de sécurité du BFF : chemin et statut seulement, jamais un jeton ni un cookie. */
export type BffSecurityEvent = {
  kind: "token_leak_masked" | "token_leak_refused" | "duplicate_refresh" | "revoke_failed";
  path: string;
  status?: number;
};

/** Contexte serveur d'une requête : rien de secret n'y est lisible. */
export type BffServer = {
  /** Pas d'accès valide mais une session à rafraîchir : rediriger vers `refreshPath(courant)`. */
  readonly needsRefresh: boolean;
  /** À passer à chaque appel généré ou à `jeflinkFetch` côté serveur. */
  readonly options: { readonly transport: Transport };
  readonly refreshPath: (next: string) => string;
};

const SAFE_METHODS = new Set(["GET", "HEAD"]);
const PROXY_METHODS = new Set(["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"]);
const FORWARDED_REQUEST_HEADERS = ["accept-language", "content-type", "idempotency-key"];
const MAX_BODY_BYTES = 64 * 1024;
// Clés des corps des endpoints de jetons, retirées avant toute réponse au navigateur.
const LEAKED_KEYS = ["tokens", "access", "refresh", "mfa_token"];
// Forme EXACTE des jetons (revue BFF, I-A) : refresh, MFA et enrôlement = préfixe +
// token_urlsafe(32), soit 43 caractères ; JWT d'accès = trois segments base64url. Bornés pour ne
// jamais prendre un texte d'utilisateur (`jfr_2026_10_01_cuisine`) pour un jeton.
const TOKEN_SOURCE = String.raw`(?<![\w-])(?:jf[rme]_[A-Za-z0-9_-]{43}|eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{20,})(?![\w-])`;
const TOKEN_PATTERN = new RegExp(TOKEN_SOURCE);
const TOKEN_MASK = "[jeton masqué]";
// Délais de la page de rebond : réseau 2G compris, puis repli vers la connexion.
const BOUNCE_FETCH_TIMEOUT_MS = 20_000;
const BOUNCE_LOCK_TIMEOUT_MS = 30_000;
const BOUNCE_FALLBACK_SECONDS = 60;
// Un refresh réussi depuis moins longtemps dans un autre onglet n'est pas refait.
const RECENT_REFRESH_MS = 10_000;
// Endpoints qui émettent ou consomment des jetons : jamais par le transport serveur.
const SERVER_ALLOWED_AUTH = new Set(["/api/auth/config/"]);
const TOKEN_ISSUING = new Set(["/api/me/fresh-start/"]);

type Ctx = {
  request: Request;
  url: URL;
  cookies: CookieJar;
  setCookies: string[];
  deviceId: string;
};

type Body = Record<string, unknown>;

class BffRejection extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string) {
    super(code);
    this.status = status;
    this.code = code;
  }
}

function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  if (body === undefined) return new Response(null, { status, headers });
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

function parseObject(text: string): Body | null {
  if (!text) return null;
  try {
    const parsed: unknown = JSON.parse(text);
    return typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)
      ? (parsed as Body)
      : null;
  } catch {
    return null;
  }
}

/** Un jeton, quel que soit l'endroit du corps (M1). */
function containsToken(text: string): boolean {
  return TOKEN_PATTERN.test(text);
}

/**
 * Masque les jetons d'un corps du proxy générique. Un jeton n'a que des caractères base64url : il
 * est toujours à l'intérieur d'une chaîne JSON, que le masque laisse valide.
 */
function maskTokens(text: string): string {
  return text.replace(new RegExp(TOKEN_SOURCE, "g"), TOKEN_MASK);
}

function isString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function randomNonce(): string {
  return btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(16))));
}

/** JSON sûr dans un <script> : aucune séquence ne peut fermer la balise. */
function scriptJson(value: unknown): string {
  return JSON.stringify(value)
    .replace(/</g, "\\u003c")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
}

function htmlAttribute(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

export function createBff(config: BffConfig) {
  if (!config.allowedOrigins.length) throw new Error("BFF : allowedOrigins est vide.");
  for (const origin of config.allowedOrigins) {
    if (!/^https?:\/\/[^/]+$/.test(origin)) throw new Error("BFF : origine autorisée invalide.");
  }
  if (config.bffSecret.length < 32) throw new Error("BFF : bffSecret trop court.");
  if (!/^https?:\/\/[^/]+$/.test(config.apiUrl)) throw new Error("BFF : apiUrl invalide.");
  if (safeNextPath(config.loginPath, "") !== config.loginPath || /[?#]/.test(config.loginPath)) {
    throw new Error("BFF : loginPath invalide.");
  }
  if (!(config.refreshMaxAgeSeconds > 0)) throw new Error("BFF : refreshMaxAgeSeconds invalide.");
  if (
    config.cookieDomain !== undefined &&
    !/^[a-z0-9-]+(\.[a-z0-9-]+)+$/i.test(config.cookieDomain)
  ) {
    throw new Error("BFF : cookieDomain invalide.");
  }
  const settings = Object.freeze({ ...config, allowedOrigins: [...config.allowedOrigins] });

  function securityEvent(event: BffSecurityEvent): void {
    try {
      if (settings.onSecurityEvent) settings.onSecurityEvent(event);
      else console.warn(JSON.stringify({ event: "bff_security", ...event }));
    } catch {
      // une alerte ne fait jamais échouer la requête
    }
  }

  // --- Réponses ------------------------------------------------------------------------------

  function finalize(response: Response, ctx: Ctx): Response {
    const headers = new Headers(response.headers);
    headers.set("Cache-Control", "private, no-store");
    headers.set("Vary", "Cookie, Authorization");
    headers.set("X-Content-Type-Options", "nosniff");
    for (const cookie of ctx.setCookies) headers.append("Set-Cookie", cookie);
    return new Response(response.body, { status: response.status, headers });
  }

  /**
   * Réponse de Django rendue au navigateur : en-têtes en liste fermée, jamais de Set-Cookie ni de
   * redirection, corps non JSON en texte brut (une page HTML d'amont ne s'affiche jamais sur
   * notre origine), et aucun jeton.
   *
   * Proxy générique (`mask`) : un jeton est masqué et signalé, la réponse passe ; un texte
   * d'utilisateur ne peut donc pas bloquer une liste (revue BFF, I-A). Endpoints d'auth
   * (`refuse`) : jeton ou clé de jeton = 502.
   */
  function relay(
    response: Response,
    upstreamText: string,
    path: string,
    mode: "mask" | "refuse",
  ): Response {
    if (response.status >= 300 && response.status < 400) {
      return json(502, { code: "bff_upstream_redirect" });
    }
    let text = upstreamText;
    if (text && mode === "refuse") {
      const parsed = parseObject(text);
      if (containsToken(text) || (parsed && LEAKED_KEYS.some((key) => key in parsed))) {
        securityEvent({ kind: "token_leak_refused", path, status: response.status });
        return json(502, { code: "bff_token_leak" });
      }
    } else if (text && containsToken(text)) {
      securityEvent({ kind: "token_leak_masked", path, status: response.status });
      text = maskTokens(text);
    }
    const headers = new Headers();
    const retryAfter = response.headers.get("retry-after");
    if (retryAfter) headers.set("Retry-After", retryAfter);
    if (text) {
      headers.set(
        "Content-Type",
        parseObject(text) !== null || /^\s*\[/.test(text)
          ? "application/json"
          : "text/plain; charset=utf-8",
      );
    }
    const empty = !text || response.status === 204 || response.status === 304;
    return new Response(empty ? null : text, { status: response.status, headers });
  }

  async function passThrough(
    response: Response,
    path: string,
    mode: "mask" | "refuse" = "mask",
  ): Promise<Response> {
    return relay(response, await response.text(), path, mode);
  }

  // --- Appels à Django -----------------------------------------------------------------------

  function clientIp(headers: Headers): string | null {
    const ip = settings.clientIp(headers);
    return ip && isIP(ip) ? ip : null;
  }

  function baseHeaders(ip: string | null, deviceId: string | null, accessToken?: string): Headers {
    const headers = new Headers({
      Accept: "application/json",
      "X-Jeflink-Bff": settings.bffSecret,
      "X-Jeflink-App": settings.app,
    });
    if (ip) headers.set("X-Jeflink-Client-Ip", ip);
    if (deviceId) headers.set("X-Install-Id", deviceId);
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
    return headers;
  }

  function callDjango(
    ctx: Ctx,
    path: string,
    init: { method: string; body?: string; accessToken?: string | undefined; search?: string },
  ): Promise<Response> {
    const headers = baseHeaders(clientIp(ctx.request.headers), ctx.deviceId, init.accessToken);
    // Liste fermée : rien d'autre du navigateur ne traverse (ni Cookie, ni X-Forwarded-*…).
    for (const name of FORWARDED_REQUEST_HEADERS) {
      const value = ctx.request.headers.get(name);
      if (value) headers.set(name, value);
    }
    if (init.body !== undefined) headers.set("Content-Type", "application/json");
    else headers.delete("Content-Type");
    return fetch(`${settings.apiUrl}${path}${init.search ?? ""}`, {
      method: init.method,
      headers,
      ...(init.body !== undefined ? { body: init.body } : {}),
      redirect: "manual",
      cache: "no-store",
    });
  }

  /** Corps lu en flux, plafonné à 64 Kio quoi que dise Content-Length (I8). */
  async function readText(request: Request): Promise<string> {
    if (!request.body) return "";
    if (Number(request.headers.get("content-length") ?? "0") > MAX_BODY_BYTES) {
      throw new BffRejection(413, "bff_body_too_large");
    }
    const reader = request.body.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_BODY_BYTES) {
        await reader.cancel().catch(() => undefined);
        throw new BffRejection(413, "bff_body_too_large");
      }
      chunks.push(value);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.byteLength;
    }
    try {
      return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    } catch {
      throw new BffRejection(400, "bff_json_invalid");
    }
  }

  /** Corps JSON objet, ou null si la requête n'a pas de corps (JSON exigé dès qu'il y en a un). */
  async function readJsonBody(ctx: Ctx): Promise<Body | null> {
    const text = await readText(ctx.request);
    if (!text) return null;
    const type = ctx.request.headers.get("content-type") ?? "";
    if (!type.toLowerCase().startsWith("application/json")) {
      throw new BffRejection(415, "bff_json_required");
    }
    const parsed = parseObject(text);
    if (parsed === null) throw new BffRejection(400, "bff_json_invalid");
    return parsed;
  }

  /** Réponse d'un endpoint qui émet des jetons : cookies posés, jetons retirés du corps. */
  async function tokenResponse(response: Response, ctx: Ctx, path: string): Promise<Response> {
    const text = await response.text();
    const body = parseObject(text);
    if (!response.ok || body === null) return relay(response, text, path, "refuse");
    const cookies: string[] = [];
    const tokens = body.tokens as Record<string, unknown> | undefined;
    if (
      typeof tokens === "object" &&
      tokens !== null &&
      isString(tokens.access) &&
      isString(tokens.refresh) &&
      isString(tokens.access_expires_at)
    ) {
      cookies.push(
        accessCookie(tokens.access, tokens.access_expires_at),
        ...refreshCookies(tokens.refresh, settings.refreshMaxAgeSeconds),
        clearMfaCookie(), // jeton MFA consommé
      );
      body.access_expires_at = tokens.access_expires_at;
    }
    if (isString(body.mfa_token)) cookies.push(mfaCookie(body.mfa_token));
    for (const key of LEAKED_KEYS) delete body[key];
    const sanitized = JSON.stringify(body);
    // Un jeton resté ailleurs dans le corps : réponse refusée, aucun cookie posé.
    if (containsToken(sanitized)) {
      securityEvent({ kind: "token_leak_refused", path, status: response.status });
      return json(502, { code: "bff_token_leak" });
    }
    ctx.setCookies.push(...cookies);
    return new Response(sanitized, {
      status: response.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  // --- Gestionnaires -------------------------------------------------------------------------

  async function withDevice(ctx: Ctx, path: string): Promise<Response> {
    // Contexte d'appareil imposé par le BFF : plateforme web et identifiant du cookie.
    const body = (await readJsonBody(ctx)) ?? {};
    const device = typeof body.device === "object" && body.device !== null ? body.device : {};
    body.device = { ...(device as object), platform: "web", install_id: ctx.deviceId };
    delete body.app;
    const response = await callDjango(ctx, path, { method: "POST", body: JSON.stringify(body) });
    return tokenResponse(response, ctx, path);
  }

  async function withMfaToken(ctx: Ctx, path: string, issuesTokens: boolean): Promise<Response> {
    const body = (await readJsonBody(ctx)) ?? {};
    body.mfa_token = ctx.cookies.get(COOKIES.mfa) ?? "";
    const response = await callDjango(ctx, path, { method: "POST", body: JSON.stringify(body) });
    return issuesTokens
      ? tokenResponse(response, ctx, path)
      : passThrough(response, path, "refuse");
  }

  async function stepUp(ctx: Ctx): Promise<Response> {
    const path = "/api/auth/mfa/totp/step-up/";
    const body = (await readJsonBody(ctx)) ?? {};
    const response = await callDjango(ctx, path, {
      method: "POST",
      body: JSON.stringify(body),
      accessToken: ctx.cookies.get(COOKIES.access),
    });
    const text = await response.text();
    if (!response.ok) return relay(response, text, path, "refuse");
    const data = parseObject(text);
    if (!data || !isString(data.access) || !isString(data.access_expires_at)) {
      return json(502, { code: "bff_upstream_invalid" });
    }
    ctx.setCookies.push(accessCookie(data.access, data.access_expires_at));
    return json(200, { access_expires_at: data.access_expires_at });
  }

  /**
   * POST du refresh. Un refresh absent n'efface que le témoin (rien à rafraîchir) ; seuls un 401
   * de Django, ou un refresh en double (fixation, M5), effacent la session. Un 429 ou une panne
   * ne déconnectent jamais (on réessaie).
   */
  async function refresh(ctx: Ctx): Promise<Response> {
    if (ctx.cookies.duplicated(COOKIES.refresh)) {
      // Fixation possible par un sous-domaine : session effacée, cookie du domaine parent aussi.
      ctx.setCookies.push(...clearSessionCookies(settings.cookieDomain));
      securityEvent({ kind: "duplicate_refresh", path: REFRESH_ENDPOINT });
      return json(401, { code: "refresh_invalid" });
    }
    const token = ctx.cookies.get(COOKIES.refresh);
    if (!token) {
      ctx.setCookies.push(serializeCookie(COOKIES.session, "", { maxAge: 0 }));
      return json(401, { code: "refresh_missing" });
    }
    const response = await callDjango(ctx, REFRESH_ENDPOINT, {
      method: "POST",
      body: JSON.stringify({ refresh: token }),
    });
    const text = await response.text();
    const body = parseObject(text);
    if (
      response.ok &&
      body &&
      isString(body.access) &&
      isString(body.refresh) &&
      isString(body.access_expires_at)
    ) {
      ctx.setCookies.push(
        accessCookie(body.access, body.access_expires_at),
        ...refreshCookies(body.refresh, settings.refreshMaxAgeSeconds),
      );
      return json(200, { access_expires_at: body.access_expires_at });
    }
    const code = isString(body?.code) ? body.code : "bff_refresh_failed";
    if (response.status === 401 || (response.status === 400 && code === "refresh_invalid")) {
      ctx.setCookies.push(...clearSessionCookies());
    }
    const status = response.ok ? 502 : response.status;
    const retryAfter = response.headers.get("retry-after");
    return json(status, { code }, retryAfter ? { "Retry-After": retryAfter } : {});
  }

  /**
   * GET du refresh : navigation d'une page dont l'accès a expiré. Aucun changement d'état ici
   * (I2) : une petite page fait le POST, sous verrou entre onglets (I3), puis revient à `next`.
   *
   * Délais (revue BFF, I-D) : 20 s pour le POST, 30 s pour obtenir le verrou ; un `meta refresh`
   * de dernier recours mène à la connexion si le script ne s'exécute pas. Un refresh réussi
   * depuis moins de 10 s dans un autre onglet n'est pas refait (aussi le repli sans Web Locks,
   * m2). Hors 401, la connexion reçoit `raison=indisponible` : elle propose de réessayer avant
   * l'OTP (m8).
   */
  function refreshBounce(ctx: Ctx): Response {
    const next = safeNextPath(ctx.url.searchParams.get("next"));
    const login = `${settings.loginPath}?next=${encodeURIComponent(next)}`;
    const retry = `${login}&raison=indisponible`;
    const data = {
      endpoint: REFRESH_ENDPOINT,
      lock: REFRESH_LOCK,
      mark: REFRESHED_AT_KEY,
      recent: RECENT_REFRESH_MS,
      fetchTimeout: BOUNCE_FETCH_TIMEOUT_MS,
      lockTimeout: BOUNCE_LOCK_TIMEOUT_MS,
      next,
      login,
      retry,
    };
    const nonce = randomNonce();
    const script = [
      "(function(){",
      `var d=${scriptJson(data)};`,
      "function go(u){location.replace(u)}",
      "function recent(){try{return Date.now()-(+localStorage.getItem(d.mark)||0)<d.recent}catch(e){return false}}",
      "function mark(){try{localStorage.setItem(d.mark,String(Date.now()))}catch(e){}}",
      "function aborter(ms){if(typeof AbortController!=='function')return null;var c=new AbortController();setTimeout(function(){c.abort()},ms);return c}",
      "function run(){if(recent()){go(d.next);return Promise.resolve()}",
      "var c=aborter(d.fetchTimeout);",
      "return fetch(d.endpoint,{method:'POST',headers:{'X-Requested-With':'jeflink'},credentials:'same-origin',cache:'no-store',signal:c?c.signal:undefined})",
      ".then(function(r){if(r.ok){mark();go(d.next)}else{go(r.status===401?d.login:d.retry)}},function(){go(d.retry)})}",
      "var L=navigator.locks;",
      "if(L&&L.request){var c=aborter(d.lockTimeout);L.request(d.lock,c?{signal:c.signal}:{},run).catch(function(){go(d.retry)})}",
      "else{run()}",
      "})();",
    ].join("");
    const html = `<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="robots" content="noindex"><meta http-equiv="refresh" content="${BOUNCE_FALLBACK_SECONDS};url=${htmlAttribute(retry)}"><noscript><meta http-equiv="refresh" content="0;url=${htmlAttribute(login)}"></noscript><script nonce="${nonce}">${script}</script></head><body></body></html>`;
    return new Response(html, {
      status: 200,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Content-Security-Policy": `default-src 'none'; script-src 'nonce-${nonce}'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`,
        "Referrer-Policy": "same-origin",
      },
    });
  }

  /**
   * Déconnexion : révoque par le refresh (marche même si l'accès a expiré, I5), et par l'accès
   * s'il est là. Les cookies sont effacés même si Django ne répond pas.
   */
  async function logout(ctx: Ctx): Promise<Response> {
    const refreshToken = ctx.cookies.get(COOKIES.refresh);
    const access = ctx.cookies.get(COOKIES.access);
    const [revoked] = await Promise.allSettled([
      refreshToken
        ? callDjango(ctx, "/api/auth/token/revoke/", {
            method: "POST",
            body: JSON.stringify({ refresh: refreshToken }),
          })
        : null,
      access ? callDjango(ctx, "/api/auth/logout/", { method: "POST", accessToken: access }) : null,
    ]);
    // Révocation non confirmée : la session reste valide côté serveur, on le signale (m3).
    const revokeStatus = revoked.status === "fulfilled" ? revoked.value?.status : undefined;
    if (refreshToken && revokeStatus !== 204) {
      securityEvent({
        kind: "revoke_failed",
        path: "/api/auth/token/revoke/",
        ...(revokeStatus !== undefined ? { status: revokeStatus } : {}),
      });
    }
    ctx.setCookies.push(...clearSessionCookies());
    return new Response(null, { status: 204 });
  }

  async function proxy(ctx: Ctx, path: string, method: string): Promise<Response> {
    const body = SAFE_METHODS.has(method) ? null : await readJsonBody(ctx);
    const response = await callDjango(ctx, path, {
      method,
      ...(body !== null ? { body: JSON.stringify(body) } : {}),
      accessToken: ctx.cookies.get(COOKIES.access),
      search: ctx.url.search,
    });
    return passThrough(response, path);
  }

  async function route(ctx: Ctx, method: string): Promise<Response> {
    const pathname = ctx.url.pathname;
    const path = pathname.endsWith("/") ? pathname : `${pathname}/`;
    const post = method === "POST";
    switch (path) {
      case REFRESH_ENDPOINT:
        if (method === "GET") return refreshBounce(ctx);
        if (post) return refresh(ctx);
        break;
      case "/api/auth/logout/":
        if (post) return logout(ctx);
        break;
      case "/api/auth/config/":
        if (method === "GET") return passThrough(await callDjango(ctx, path, { method }), path);
        break;
      case "/api/auth/otp/request/":
      case "/api/auth/otp/resend/":
        if (post) {
          const body = (await readJsonBody(ctx)) ?? {};
          delete body.app; // imposé par l'en-tête du BFF
          const response = await callDjango(ctx, path, { method, body: JSON.stringify(body) });
          return passThrough(response, path, "refuse");
        }
        break;
      case "/api/auth/otp/verify/":
      case "/api/auth/phone-change/confirm/":
        if (post) return withDevice(ctx, path);
        break;
      case "/api/auth/mfa/totp/setup/":
        if (post) return withMfaToken(ctx, path, false);
        break;
      case "/api/auth/mfa/totp/confirm/":
      case "/api/auth/mfa/totp/verify/":
        if (post) return withMfaToken(ctx, path, true);
        break;
      case "/api/auth/mfa/totp/step-up/":
        if (post) return stepUp(ctx);
        break;
      case "/api/me/fresh-start/":
        if (post) {
          const body = await readJsonBody(ctx);
          const response = await callDjango(ctx, path, {
            method,
            ...(body !== null ? { body: JSON.stringify(body) } : {}),
            accessToken: ctx.cookies.get(COOKIES.access),
          });
          return tokenResponse(response, ctx, path);
        }
        break;
      default: {
        // Aucun autre endpoint d'auth via le proxy, quelle que soit la casse.
        if (path.toLowerCase().startsWith("/api/auth/")) break;
        const safe = safeApiPath(pathname);
        if (!safe) return json(404, { code: "not_found" });
        if (!PROXY_METHODS.has(method)) break;
        return proxy(ctx, safe, method);
      }
    }
    return json(405, { code: "method_not_allowed" });
  }

  // --- Point d'entrée ------------------------------------------------------------------------

  async function handle(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const cookies = readCookies(request.headers);
    const existingDevice = cookies.get(COOKIES.device);
    const ctx: Ctx = {
      request,
      url,
      cookies,
      setCookies: [],
      // Identifiant d'appareil : un UUID, sinon régénéré (M6).
      deviceId: isDeviceId(existingDevice) ? existingDevice : crypto.randomUUID(),
    };
    if (ctx.deviceId !== existingDevice) ctx.setCookies.push(deviceCookie(ctx.deviceId));
    try {
      const method = request.method.toUpperCase();
      const isRefreshNavigation =
        method === "GET" && url.pathname.replace(/\/?$/, "/") === REFRESH_ENDPOINT;
      if (!SAFE_METHODS.has(method)) {
        // CSRF : Origin exact, y compris sur /api/auth/* (spec 001, « BFF Next »).
        const origin = request.headers.get("origin");
        if (!origin || !settings.allowedOrigins.includes(origin)) {
          throw new BffRejection(403, "bff_origin_forbidden");
        }
      }
      if (!isRefreshNavigation && request.headers.get("x-requested-with") !== "jeflink") {
        throw new BffRejection(403, "bff_requested_with_missing");
      }
      return finalize(await route(ctx, method), ctx);
    } catch (error) {
      if (error instanceof BffRejection) {
        return finalize(json(error.status, { code: error.code }), ctx);
      }
      return finalize(json(502, { code: "bff_upstream_unavailable" }), ctx);
    }
  }

  function refreshRedirectPath(next: string): string {
    return `${REFRESH_ENDPOINT}?next=${encodeURIComponent(safeNextPath(next))}`;
  }

  /**
   * Contexte serveur d'une requête de page (I6). Le transport n'accepte que des chemins d'API sûrs
   * hors endpoints de jetons, impose `no-store` et la liste fermée d'en-têtes ; le jeton d'accès
   * et le secret ne sortent jamais de la fermeture. Prend les en-têtes de la requête entrante
   * (`await headers()` dans un Server Component, m7) ou la requête elle-même.
   */
  function server(source: Request | Headers): BffServer {
    const incoming = source instanceof Headers ? source : source.headers;
    const cookies = readCookies(incoming);
    const access = cookies.get(COOKIES.access);
    const device = cookies.get(COOKIES.device);
    const ip = clientIp(incoming);
    const language = incoming.get("accept-language");
    const transport: Transport = (path, init) => {
      // Chemin brut contrôlé AVANT la normalisation de `new URL` (revue BFF, I-C).
      if (hasUnsafePathSegments(path)) {
        return Promise.reject(new Error("BFF : chemin refusé pour un appel serveur."));
      }
      const target = new URL(path, "https://bff.invalid");
      const safe = target.origin === "https://bff.invalid" ? safeApiPath(target.pathname) : null;
      const lowered = target.pathname.toLowerCase();
      if (
        !safe ||
        TOKEN_ISSUING.has(lowered) ||
        (lowered.startsWith("/api/auth/") && !SERVER_ALLOWED_AUTH.has(lowered))
      ) {
        return Promise.reject(new Error("BFF : chemin refusé pour un appel serveur."));
      }
      const given = new Headers(init.headers);
      const headers = baseHeaders(ip, isDeviceId(device) ? device : null, access);
      for (const name of FORWARDED_REQUEST_HEADERS) {
        const value = given.get(name);
        if (value) headers.set(name, value);
      }
      if (!headers.has("accept-language") && language) headers.set("accept-language", language);
      return fetch(`${settings.apiUrl}${safe}${target.search}`, {
        method: init.method ?? "GET",
        headers,
        ...(init.body !== undefined && init.body !== null ? { body: init.body } : {}),
        ...(init.signal ? { signal: init.signal } : {}),
        redirect: "manual",
        cache: "no-store",
      });
    };
    return Object.freeze({
      needsRefresh: !access && cookies.has(COOKIES.session),
      options: Object.freeze({ transport }),
      refreshPath: refreshRedirectPath,
    });
  }

  return Object.freeze({ handle, server, refreshRedirectPath });
}
