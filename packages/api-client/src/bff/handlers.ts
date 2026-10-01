// BFF Next de Jeflink (spec 001, « BFF Next » ; ADR 0007 ; S4, S6, S9, S10, S20).
//
// Un seul point d'entrée, `handle(request)`, monté derrière la route attrape-tout de l'app
// (`app/api/[...path]/route.ts`) : les endpoints qui émettent des jetons ont leurs gestionnaires,
// tout le reste passe par le proxy durci. Aucun état de module : la configuration est figée par
// `createBff`, et chaque requête porte ses propres cookies et en-têtes.

import {
  COOKIES,
  accessCookie,
  clearSessionCookies,
  deviceCookie,
  mfaCookie,
  readCookies,
  refreshCookie,
} from "./cookies.ts";
import { safeApiPath, safeNextPath } from "./paths.ts";

export type BffConfig = {
  /** Contexte imposé à Django : jamais choisi par le navigateur (S10). */
  app: "web" | "console";
  /** API Django sur le réseau interne, par son hôte interne (ex. http://api:8000). */
  apiUrl: string;
  /** Origines exactes autorisées pour toute requête non GET (CSRF). */
  allowedOrigins: string[];
  /** Secret partagé avec Django (BFF_SHARED_SECRETS), jamais en NEXT_PUBLIC_. */
  bffSecret: string;
  /** IP cliente lue depuis UNE source fiable de l'hébergeur ; jamais X-Forwarded-For brut. */
  clientIp: (request: Request) => string | null;
  /** Durée du cookie de refresh : 30 j (web), 12 h (console). */
  refreshMaxAgeSeconds: number;
  /** Page de connexion, cible des redirections après un refresh impossible. */
  loginPath: string;
};

export type ServerCallOptions = {
  baseUrl: string;
  accessToken?: string;
  headers: Record<string, string>;
};

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const FORWARDED_REQUEST_HEADERS = ["accept-language", "content-type", "idempotency-key"];
const FORWARDED_RESPONSE_HEADERS = ["content-type", "retry-after"];
const MAX_BODY_BYTES = 64 * 1024;
const LEAKED_KEYS = ["tokens", "access", "refresh", "mfa_token"];

type Ctx = {
  request: Request;
  url: URL;
  cookies: Map<string, string>;
  setCookies: string[];
  deviceId: string;
};

class BffRejection extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string) {
    super(code);
    this.status = status;
    this.code = code;
  }
}

export function createBff(config: BffConfig) {
  if (!config.allowedOrigins.length) throw new Error("BFF : allowedOrigins est vide.");
  if (config.bffSecret.length < 32) throw new Error("BFF : bffSecret trop court.");
  if (!/^https?:\/\/[^/]+$/.test(config.apiUrl)) throw new Error("BFF : apiUrl invalide.");
  const settings = Object.freeze({ ...config, allowedOrigins: [...config.allowedOrigins] });

  // --- Réponses ------------------------------------------------------------------------------

  function finalize(response: Response, ctx: Ctx): Response {
    const headers = new Headers(response.headers);
    headers.set("Cache-Control", "private, no-store");
    headers.set("Vary", "Cookie, Authorization");
    for (const cookie of ctx.setCookies) headers.append("Set-Cookie", cookie);
    return new Response(response.body, { status: response.status, headers });
  }

  function json(status: number, body: unknown): Response {
    return new Response(body === undefined ? null : JSON.stringify(body), {
      status,
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
    });
  }

  // --- Appels à Django -----------------------------------------------------------------------

  function djangoHeaders(ctx: Ctx | null, request: Request, accessToken?: string): Headers {
    const headers = new Headers({
      Accept: "application/json",
      "X-Jeflink-Bff": settings.bffSecret,
      "X-Jeflink-App": settings.app,
    });
    const ip = settings.clientIp(request);
    if (ip) headers.set("X-Jeflink-Client-Ip", ip);
    if (ctx) headers.set("X-Install-Id", ctx.deviceId);
    if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
    // Liste fermée : rien d'autre du navigateur ne traverse (ni Cookie, ni X-Forwarded-*…).
    for (const name of FORWARDED_REQUEST_HEADERS) {
      const value = request.headers.get(name);
      if (value) headers.set(name, value);
    }
    return headers;
  }

  function callDjango(
    ctx: Ctx,
    path: string,
    init: {
      method: string;
      body?: string;
      accessToken?: string | undefined;
      search?: string;
    },
  ): Promise<Response> {
    const headers = djangoHeaders(ctx, ctx.request, init.accessToken);
    if (init.body !== undefined) headers.set("Content-Type", "application/json");
    return fetch(`${settings.apiUrl}${path}${init.search ?? ""}`, {
      method: init.method,
      headers,
      ...(init.body !== undefined ? { body: init.body } : {}),
      redirect: "manual",
    });
  }

  async function readJsonBody(ctx: Ctx): Promise<Record<string, unknown>> {
    const type = ctx.request.headers.get("content-type") ?? "";
    if (!type.toLowerCase().startsWith("application/json")) {
      throw new BffRejection(415, "bff_json_required");
    }
    const declared = Number(ctx.request.headers.get("content-length") ?? "0");
    if (declared > MAX_BODY_BYTES) throw new BffRejection(413, "bff_body_too_large");
    const text = await ctx.request.text();
    if (new TextEncoder().encode(text).length > MAX_BODY_BYTES) {
      throw new BffRejection(413, "bff_body_too_large");
    }
    if (!text) return {};
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      throw new BffRejection(400, "bff_json_invalid");
    }
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      throw new BffRejection(400, "bff_json_invalid");
    }
    return parsed as Record<string, unknown>;
  }

  async function passThrough(response: Response): Promise<Response> {
    const text = await response.text();
    if (text) {
      try {
        const parsed: unknown = JSON.parse(text);
        if (
          typeof parsed === "object" &&
          parsed !== null &&
          LEAKED_KEYS.some((key) => key in parsed)
        ) {
          // Défense en profondeur : un jeton ne doit jamais atteindre le navigateur.
          return json(502, { code: "bff_token_leak" });
        }
      } catch {
        // corps non JSON (page d'erreur) : transmis tel quel
      }
    }
    const headers = new Headers();
    for (const name of FORWARDED_RESPONSE_HEADERS) {
      const value = response.headers.get(name);
      if (value) headers.set(name, value);
    }
    // Les Set-Cookie de Django ne sont jamais transmis (S9).
    return new Response(text || null, { status: response.status, headers });
  }

  /** Réponse d'un endpoint qui émet des jetons : cookies posés, jetons retirés du corps. */
  async function tokenResponse(response: Response, ctx: Ctx): Promise<Response> {
    const text = await response.text();
    let body: Record<string, unknown> | null = null;
    try {
      const parsed: unknown = text ? JSON.parse(text) : null;
      if (typeof parsed === "object" && parsed !== null) body = parsed as Record<string, unknown>;
    } catch {
      body = null;
    }
    if (!response.ok || body === null) {
      return new Response(text || null, {
        status: response.status,
        headers: { "Content-Type": response.headers.get("content-type") ?? "application/json" },
      });
    }
    const tokens = body.tokens as
      { access?: string; refresh?: string; access_expires_at?: string } | undefined;
    if (tokens?.access && tokens.refresh && tokens.access_expires_at) {
      ctx.setCookies.push(
        accessCookie(tokens.access, tokens.access_expires_at),
        refreshCookie(tokens.refresh, settings.refreshMaxAgeSeconds),
        ...clearSessionCookies().slice(2), // jeton MFA consommé
      );
      body.access_expires_at = tokens.access_expires_at;
    }
    if (typeof body.mfa_token === "string") ctx.setCookies.push(mfaCookie(body.mfa_token));
    for (const key of LEAKED_KEYS) delete body[key];
    return json(response.status, body);
  }

  // --- Gestionnaires -------------------------------------------------------------------------

  async function withDevice(ctx: Ctx, path: string): Promise<Response> {
    // Contexte d'appareil imposé par le BFF : plateforme web et identifiant du cookie.
    const body = await readJsonBody(ctx);
    const device = typeof body.device === "object" && body.device !== null ? body.device : {};
    body.device = { ...(device as object), platform: "web", install_id: ctx.deviceId };
    delete body.app;
    const response = await callDjango(ctx, path, { method: "POST", body: JSON.stringify(body) });
    return tokenResponse(response, ctx);
  }

  async function withMfaToken(ctx: Ctx, path: string, issuesTokens: boolean): Promise<Response> {
    const body = await readJsonBody(ctx);
    body.mfa_token = ctx.cookies.get(COOKIES.mfa) ?? "";
    const response = await callDjango(ctx, path, { method: "POST", body: JSON.stringify(body) });
    return issuesTokens ? tokenResponse(response, ctx) : passThrough(response);
  }

  async function stepUp(ctx: Ctx): Promise<Response> {
    const body = await readJsonBody(ctx);
    const response = await callDjango(ctx, "/api/auth/mfa/totp/step-up/", {
      method: "POST",
      body: JSON.stringify(body),
      accessToken: ctx.cookies.get(COOKIES.access),
    });
    if (!response.ok) return passThrough(response);
    const data = (await response.json()) as { access: string; access_expires_at: string };
    ctx.setCookies.push(accessCookie(data.access, data.access_expires_at));
    return json(200, { access_expires_at: data.access_expires_at });
  }

  async function refresh(ctx: Ctx): Promise<{ ok: boolean; status: number; body: unknown }> {
    const token = ctx.cookies.get(COOKIES.refresh);
    if (!token) {
      ctx.setCookies.push(...clearSessionCookies());
      return { ok: false, status: 401, body: { code: "refresh_invalid" } };
    }
    const response = await callDjango(ctx, "/api/auth/token/refresh/", {
      method: "POST",
      body: JSON.stringify({ refresh: token }),
    });
    const body = (await response.json().catch(() => ({}))) as Record<string, string>;
    if (response.ok && body.access && body.refresh && body.access_expires_at) {
      ctx.setCookies.push(
        accessCookie(body.access, body.access_expires_at),
        refreshCookie(body.refresh, settings.refreshMaxAgeSeconds),
      );
      return { ok: true, status: 200, body: { access_expires_at: body.access_expires_at } };
    }
    // 401 : session finie, cookies effacés. 429 ou 5xx : jamais une déconnexion (on réessaie).
    if (response.status === 401) ctx.setCookies.push(...clearSessionCookies());
    return { ok: false, status: response.status, body };
  }

  async function refreshRedirect(ctx: Ctx): Promise<Response> {
    const next = safeNextPath(ctx.url.searchParams.get("next"));
    const result = await refresh(ctx);
    const target = result.ok
      ? next
      : `${settings.loginPath}?next=${encodeURIComponent(next)}${
          result.status === 401 ? "" : "&raison=indisponible"
        }`;
    return new Response(null, { status: 303, headers: { Location: target } });
  }

  async function logout(ctx: Ctx): Promise<Response> {
    const access = ctx.cookies.get(COOKIES.access);
    if (access) {
      await callDjango(ctx, "/api/auth/logout/", { method: "POST", accessToken: access }).catch(
        () => undefined,
      );
    }
    ctx.setCookies.push(...clearSessionCookies());
    return new Response(null, { status: 204 });
  }

  async function proxy(ctx: Ctx, path: string): Promise<Response> {
    const method = ctx.request.method.toUpperCase();
    const body = UNSAFE_METHODS.has(method) ? JSON.stringify(await readJsonBody(ctx)) : undefined;
    const response = await callDjango(ctx, path, {
      method,
      ...(body !== undefined && method !== "DELETE" ? { body } : {}),
      accessToken: ctx.cookies.get(COOKIES.access),
      search: ctx.url.search,
    });
    return passThrough(response);
  }

  async function route(ctx: Ctx): Promise<Response> {
    const path = ctx.url.pathname.endsWith("/") ? ctx.url.pathname : `${ctx.url.pathname}/`;
    const method = ctx.request.method.toUpperCase();
    const post = method === "POST";
    switch (path) {
      case "/api/auth/token/refresh/": {
        if (method === "GET") return refreshRedirect(ctx);
        if (!post) break;
        const result = await refresh(ctx);
        return json(result.status, result.body);
      }
      case "/api/auth/logout/":
        if (post) return logout(ctx);
        break;
      case "/api/auth/config/":
        if (method === "GET") return passThrough(await callDjango(ctx, path, { method }));
        break;
      case "/api/auth/otp/request/":
      case "/api/auth/otp/resend/":
        if (post) {
          const body = await readJsonBody(ctx);
          delete body.app; // imposé par l'en-tête du BFF
          return passThrough(await callDjango(ctx, path, { method, body: JSON.stringify(body) }));
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
          const response = await callDjango(ctx, path, {
            method,
            accessToken: ctx.cookies.get(COOKIES.access),
          });
          return tokenResponse(response, ctx);
        }
        break;
      default: {
        if (path.startsWith("/api/auth/")) break; // aucun autre endpoint d'auth via le proxy
        const safe = safeApiPath(ctx.url.pathname);
        if (!safe) return json(404, { code: "not_found" });
        return proxy(ctx, safe);
      }
    }
    return json(405, { code: "method_not_allowed" });
  }

  // --- Point d'entrée ------------------------------------------------------------------------

  async function handle(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const cookies = readCookies(request);
    const ctx: Ctx = {
      request,
      url,
      cookies,
      setCookies: [],
      deviceId: cookies.get(COOKIES.device) ?? crypto.randomUUID(),
    };
    if (!cookies.has(COOKIES.device)) ctx.setCookies.push(deviceCookie(ctx.deviceId));
    try {
      const method = request.method.toUpperCase();
      const isRefreshNavigation =
        method === "GET" && url.pathname.replace(/\/?$/, "/") === "/api/auth/token/refresh/";
      if (UNSAFE_METHODS.has(method)) {
        // CSRF : Origin exact, y compris sur /api/auth/* (spec 001, « BFF Next »).
        const origin = request.headers.get("origin");
        if (!origin || !settings.allowedOrigins.includes(origin)) {
          throw new BffRejection(403, "bff_origin_forbidden");
        }
      }
      if (!isRefreshNavigation && request.headers.get("x-requested-with") !== "jeflink") {
        throw new BffRejection(403, "bff_requested_with_missing");
      }
      return finalize(await route(ctx), ctx);
    } catch (error) {
      if (error instanceof BffRejection) {
        return finalize(json(error.status, { code: error.code }), ctx);
      }
      return finalize(json(502, { code: "bff_upstream_unavailable" }), ctx);
    }
  }

  /**
   * Options d'appel côté serveur (Server Components, actions) : à passer à chaque appel
   * `jeflinkFetch` ou hook généré. `needsRefresh` : pas d'accès valide, rediriger vers
   * `refreshRedirectPath(cheminCourant)`.
   */
  function serverCallOptions(request: Request): {
    options: ServerCallOptions;
    needsRefresh: boolean;
  } {
    const cookies = readCookies(request);
    const accessToken = cookies.get(COOKIES.access);
    const headers = Object.fromEntries(djangoHeaders(null, request, undefined).entries());
    delete headers["accept-language"];
    delete headers["content-type"];
    delete headers["idempotency-key"];
    const lang = request.headers.get("accept-language");
    if (lang) headers["accept-language"] = lang;
    const device = cookies.get(COOKIES.device);
    if (device) headers["x-install-id"] = device;
    return {
      options: { baseUrl: settings.apiUrl, ...(accessToken ? { accessToken } : {}), headers },
      needsRefresh: !accessToken && cookies.has(COOKIES.refresh),
    };
  }

  return {
    handle,
    serverCallOptions,
    refreshRedirectPath: (next: string) =>
      `/api/auth/token/refresh/?next=${encodeURIComponent(safeNextPath(next))}`,
  };
}
