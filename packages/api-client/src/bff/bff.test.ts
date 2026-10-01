// Tests du BFF (spec 001, packages/api-client tâche 2) : concurrence, traversée de chemin, en-têtes.
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";

import { COOKIES } from "./cookies.ts";
import { createBff } from "./handlers.ts";
import { safeApiPath, safeNextPath } from "./paths.ts";

const ORIGIN = "https://jeflink.test";
const SECRET = "test-bff-secret-not-secret-0123456789abcd";

type Upstream = { url: string; method: string; headers: Headers; body: string | undefined };
let upstream: Upstream[];
let handler: (call: Upstream) => Response | Promise<Response>;
const realFetch = globalThis.fetch;

const bff = createBff({
  app: "web",
  apiUrl: "http://api:8000",
  allowedOrigins: [ORIGIN],
  bffSecret: SECRET,
  clientIp: (request) => request.headers.get("x-real-ip"),
  refreshMaxAgeSeconds: 30 * 24 * 3600,
  loginPath: "/connexion",
});

function jsonResponse(
  status: number,
  body: unknown,
  headers: Record<string, string> = {},
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

beforeEach(() => {
  upstream = [];
  handler = () => jsonResponse(200, { ok: true });
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const call: Upstream = {
      url: String(input),
      method: init?.method ?? "GET",
      headers: new Headers(init?.headers),
      body: typeof init?.body === "string" ? init.body : undefined,
    };
    upstream.push(call);
    return handler(call);
  }) as typeof fetch;
});

afterEach(() => {
  globalThis.fetch = realFetch;
});

function browser(
  path: string,
  options: {
    method?: string;
    body?: unknown;
    cookies?: Record<string, string>;
    headers?: Record<string, string>;
  } = {},
): Request {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = {
    "X-Requested-With": "jeflink",
    "x-real-ip": "41.82.1.2",
    ...(method === "GET" ? {} : { Origin: ORIGIN, "Content-Type": "application/json" }),
    ...options.headers,
  };
  const jar = { [COOKIES.device]: "appareil-1", ...options.cookies };
  headers.cookie = Object.entries(jar)
    .map(([name, value]) => `${name}=${value}`)
    .join("; ");
  return new Request(`${ORIGIN}${path}`, {
    method,
    headers,
    ...(options.body !== undefined ? { body: JSON.stringify(options.body) } : {}),
  });
}

function setCookies(response: Response): string[] {
  return response.headers.getSetCookie();
}

describe("CSRF", () => {
  it("POST sans Origin, ou d'une autre origine, refusé — y compris /api/auth/*", async () => {
    for (const origin of [undefined, "https://evil.test"]) {
      const request = browser("/api/auth/otp/request/", { method: "POST", body: { phone: "77" } });
      const headers = new Headers(request.headers);
      if (origin) headers.set("Origin", origin);
      else headers.delete("Origin");
      const response = await bff.handle(new Request(request, { headers }));
      assert.equal(response.status, 403);
      assert.deepEqual(await response.json(), { code: "bff_origin_forbidden" });
    }
    assert.equal(upstream.length, 0);
  });

  it("X-Requested-With exigé, sauf pour la redirection de refresh", async () => {
    const response = await bff.handle(browser("/api/me/", { headers: { "X-Requested-With": "" } }));
    assert.equal(response.status, 403);
    const navigation = new Request(`${ORIGIN}/api/auth/token/refresh/?next=/compte`);
    assert.equal((await bff.handle(navigation)).status, 303);
  });

  it("JSON imposé hors GET", async () => {
    const response = await bff.handle(
      browser("/api/me/", { method: "PATCH", headers: { "Content-Type": "text/plain" } }),
    );
    assert.equal(response.status, 415);
    assert.equal(upstream.length, 0);
  });
});

describe("proxy durci", () => {
  it("routes internes et traversées refusées sans appel à Django", async () => {
    for (const path of [
      "/api/internal/x",
      "/api/webhooks/wiipay",
      "/api/schema/",
      "/api/docs/",
      "/api/%2e%2e/admin/",
      "/api/me%2fsessions/",
      "/api/me/..%2f..%2fadmin",
      "/api/auth/inconnu/",
    ]) {
      const response = await bff.handle(browser(path));
      assert.ok([404, 405].includes(response.status), `${path} → ${response.status}`);
    }
    assert.equal(upstream.length, 0);
  });

  it("safeApiPath refuse encodages, antislash et doubles barres", () => {
    for (const path of [
      "/api/%2E%2E/x",
      "/api/a%2fb",
      "/api/a%5cb",
      "/api/a\\b",
      "/api//x",
      "/api/../x",
      "/admin/",
      "http://x/api/",
    ]) {
      assert.equal(safeApiPath(path), null, path);
    }
    assert.equal(safeApiPath("/api/me/sessions/"), "/api/me/sessions/");
  });

  it("liste fermée d'en-têtes ; jeton du cookie ; secret et IP du BFF", async () => {
    await bff.handle(
      browser("/api/me/?page=2", {
        cookies: { [COOKIES.access]: "ACCES" },
        headers: {
          Authorization: "Bearer FORGE",
          "X-Forwarded-For": "1.2.3.4",
          "X-Jeflink-Bff": "faux",
          "X-Jeflink-Client-Ip": "1.2.3.4",
          "X-Jeflink-App": "console",
          "Accept-Language": "wo",
        },
      }),
    );
    const [call] = upstream;
    assert.equal(call?.url, "http://api:8000/api/me/?page=2");
    assert.equal(call?.headers.get("authorization"), "Bearer ACCES");
    assert.equal(call?.headers.get("x-jeflink-bff"), SECRET);
    assert.equal(call?.headers.get("x-jeflink-client-ip"), "41.82.1.2");
    assert.equal(call?.headers.get("x-jeflink-app"), "web");
    assert.equal(call?.headers.get("x-install-id"), "appareil-1");
    assert.equal(call?.headers.get("accept-language"), "wo");
    assert.equal(call?.headers.get("x-forwarded-for"), null);
    assert.equal(call?.headers.get("cookie"), null);
  });

  it("Set-Cookie de Django jamais transmis ; en-têtes de cache sur toute réponse", async () => {
    handler = () => jsonResponse(200, { ok: 1 }, { "Set-Cookie": "sessionid=django" });
    const response = await bff.handle(browser("/api/me/"));
    assert.ok(!setCookies(response).some((c) => c.startsWith("sessionid")));
    assert.equal(response.headers.get("cache-control"), "private, no-store");
    assert.equal(response.headers.get("vary"), "Cookie, Authorization");
  });

  it("un jeton dans une réponse du proxy n'atteint jamais le navigateur", async () => {
    handler = () => jsonResponse(200, { tokens: { access: "x" } });
    const response = await bff.handle(browser("/api/me/"));
    assert.equal(response.status, 502);
    assert.deepEqual(await response.json(), { code: "bff_token_leak" });
  });
});

describe("jetons en cookies", () => {
  const authenticated = {
    status: "authenticated",
    user: { public_id: "u" },
    tokens: {
      access: "ACC",
      refresh: "jfr_REF",
      access_expires_at: new Date(Date.now() + 900_000).toISOString(),
    },
  };

  it("otp/verify : cookies posés, jetons retirés, appareil et app imposés", async () => {
    handler = () => jsonResponse(200, authenticated);
    const response = await bff.handle(
      browser("/api/auth/otp/verify/", {
        method: "POST",
        body: {
          code: "123456",
          app: "console",
          device: { platform: "ios", install_id: "forge", label: "Chrome" },
        },
      }),
    );
    const body = await response.json();
    assert.equal(body.tokens, undefined);
    assert.equal(body.status, "authenticated");
    const cookies = setCookies(response);
    assert.ok(
      cookies.some(
        (c) =>
          c.startsWith(`${COOKIES.access}=ACC`) && c.includes("HttpOnly") && c.includes("Secure"),
      ),
    );
    const refresh = cookies.find((c) => c.startsWith(`${COOKIES.refresh}=`));
    assert.ok(refresh?.includes("Path=/api/auth") && refresh.includes("SameSite=Strict"));
    const sent = JSON.parse(upstream[0]?.body ?? "{}");
    assert.equal(sent.app, undefined);
    assert.deepEqual(sent.device, { platform: "web", install_id: "appareil-1", label: "Chrome" });
  });

  it("parcours Ops : jeton MFA en cookie, jamais dans le corps", async () => {
    handler = () => jsonResponse(200, { status: "mfa_required", mfa_token: "jfm_SECRET" });
    const first = await bff.handle(
      browser("/api/auth/otp/verify/", { method: "POST", body: { code: "1" } }),
    );
    assert.deepEqual(await first.json(), { status: "mfa_required" });
    assert.ok(
      setCookies(first).some(
        (c) => c.startsWith(`${COOKIES.mfa}=jfm_SECRET`) && c.includes("Max-Age=300"),
      ),
    );
    handler = () => jsonResponse(200, authenticated);
    await bff.handle(
      browser("/api/auth/mfa/totp/verify/", {
        method: "POST",
        body: { code: "111111", mfa_token: "forge" },
        cookies: { [COOKIES.mfa]: "jfm_SECRET" },
      }),
    );
    assert.equal(JSON.parse(upstream[1]?.body ?? "{}").mfa_token, "jfm_SECRET");
  });

  it("refresh : succès pose les cookies, 401 les efface, 429 ne déconnecte pas", async () => {
    handler = () =>
      jsonResponse(200, {
        access: "A2",
        refresh: "jfr_R2",
        access_expires_at: new Date(Date.now() + 900_000).toISOString(),
      });
    const ok = await bff.handle(
      browser("/api/auth/token/refresh/", {
        method: "POST",
        cookies: { [COOKIES.refresh]: "jfr_R1" },
      }),
    );
    assert.equal(ok.status, 200);
    assert.equal(JSON.parse(upstream[0]?.body ?? "{}").refresh, "jfr_R1");
    assert.ok(setCookies(ok).some((c) => c.startsWith(`${COOKIES.refresh}=jfr_R2`)));
    assert.equal((await ok.json()).refresh, undefined);

    handler = () => jsonResponse(401, { code: "session_revoked" });
    const gone = await bff.handle(
      browser("/api/auth/token/refresh/", {
        method: "POST",
        cookies: { [COOKIES.refresh]: "jfr_R2" },
      }),
    );
    assert.ok(
      setCookies(gone).some((c) => c.startsWith(`${COOKIES.refresh}=;`) && c.includes("Max-Age=0")),
    );

    handler = () => jsonResponse(429, { code: "throttled" });
    const busy = await bff.handle(
      browser("/api/auth/token/refresh/", {
        method: "POST",
        cookies: { [COOKIES.refresh]: "jfr_R2" },
      }),
    );
    assert.equal(busy.status, 429);
    assert.ok(!setCookies(busy).some((c) => c.startsWith(`${COOKIES.refresh}=`)));
  });

  it("redirection de refresh : next validé, connexion en cas d'échec", async () => {
    handler = () =>
      jsonResponse(200, {
        access: "A",
        refresh: "jfr_B",
        access_expires_at: new Date(Date.now() + 900_000).toISOString(),
      });
    const ok = await bff.handle(
      new Request(`${ORIGIN}/api/auth/token/refresh/?next=//evil.test/x`, {
        headers: { cookie: `${COOKIES.refresh}=jfr_A` },
      }),
    );
    assert.equal(ok.headers.get("location"), "/");
    const none = await bff.handle(new Request(`${ORIGIN}/api/auth/token/refresh/?next=/compte`));
    assert.equal(none.headers.get("location"), "/connexion?next=%2Fcompte");
  });

  it("déconnexion : Django prévenu, cookies de session effacés, appareil gardé", async () => {
    handler = () => new Response(null, { status: 204 });
    const response = await bff.handle(
      browser("/api/auth/logout/", { method: "POST", cookies: { [COOKIES.access]: "ACC" } }),
    );
    assert.equal(response.status, 204);
    assert.equal(upstream[0]?.headers.get("authorization"), "Bearer ACC");
    const cookies = setCookies(response);
    assert.ok(cookies.some((c) => c.startsWith(`${COOKIES.access}=;`)));
    assert.ok(!cookies.some((c) => c.startsWith(`${COOKIES.device}=`)));
  });
});

describe("aucun état partagé entre requêtes (S4)", () => {
  it("deux requêtes concurrentes de comptes différents ne se mélangent pas", async () => {
    handler = async (call) => {
      await new Promise((resolve) =>
        setTimeout(resolve, call.headers.get("authorization") === "Bearer A" ? 30 : 5),
      );
      return jsonResponse(200, { vu: call.headers.get("authorization") });
    };
    const [a, b] = await Promise.all([
      bff.handle(
        browser("/api/me/", { cookies: { [COOKIES.access]: "A", [COOKIES.device]: "dev-a" } }),
      ),
      bff.handle(
        browser("/api/me/", { cookies: { [COOKIES.access]: "B", [COOKIES.device]: "dev-b" } }),
      ),
    ]);
    assert.deepEqual(await a.json(), { vu: "Bearer A" });
    assert.deepEqual(await b.json(), { vu: "Bearer B" });
  });

  it("options serveur : jeton par appel, jamais de singleton", () => {
    const { options, needsRefresh } = bff.serverCallOptions(
      browser("/compte", { cookies: { [COOKIES.access]: "SRV" } }),
    );
    assert.equal(options.accessToken, "SRV");
    assert.equal(options.baseUrl, "http://api:8000");
    assert.equal(options.headers["x-jeflink-bff"], SECRET);
    assert.equal(needsRefresh, false);
    const expired = bff.serverCallOptions(
      browser("/compte", { cookies: { [COOKIES.refresh]: "jfr_x" } }),
    );
    assert.equal(expired.needsRefresh, true);
  });
});

describe("safeNextPath (S20)", () => {
  it("chemin relatif interne seulement", () => {
    for (const bad of [
      "https://evil.test",
      "//evil.test",
      "/\\evil.test",
      "javascript:alert(1)",
      "compte",
      "/a\nb",
    ]) {
      assert.equal(safeNextPath(bad), "/", bad);
    }
    assert.equal(safeNextPath("/compte?onglet=2#x"), "/compte?onglet=2#x");
  });
});

describe("configuration", () => {
  it("refuse une configuration dangereuse", () => {
    assert.throws(() =>
      createBff({
        app: "web",
        apiUrl: "http://api:8000",
        allowedOrigins: [],
        bffSecret: SECRET,
        clientIp: () => null,
        refreshMaxAgeSeconds: 1,
        loginPath: "/",
      }),
    );
    assert.throws(() =>
      createBff({
        app: "web",
        apiUrl: "http://api:8000",
        allowedOrigins: [ORIGIN],
        bffSecret: "court",
        clientIp: () => null,
        refreshMaxAgeSeconds: 1,
        loginPath: "/",
      }),
    );
  });
});
