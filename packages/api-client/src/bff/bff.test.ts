// Tests du BFF (spec 001, packages/api-client tâche 2, et corrections de la revue sécurité) :
// CSRF, traversée de chemin, en-têtes, jetons en cookies, refresh, état par requête.
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";
import { runInNewContext } from "node:vm";

import { jeflinkFetch } from "../http.ts";
import { COOKIES } from "./cookies.ts";
import { type BffConfig, type BffSecurityEvent, createBff } from "./handlers.ts";
import { safeApiPath, safeNextPath } from "./paths.ts";

const ORIGIN = "https://jeflink.test";
const SECRET = "test-bff-secret-not-secret-0123456789abcd";
const DEVICE = "6f1c2b9e-3a4d-4c5e-9f00-1a2b3c4d5e6f";
// Formes réalistes, valeurs factices : servent à vérifier la détection de fuite.
const FAKE_REFRESH = `jfr_${"x".repeat(43)}`;
// Assemblé à l'exécution : aucun littéral de forme JWT dans le dépôt (gitleaks).
const FAKE_JWT = [
  "eyJhbGciOiJIUzI1NiJ9",
  "eyJzdWIiOiJ0ZXN0LWZhY3RpY2UifQ",
  "signature-factice-0123456789",
].join(".");

type Upstream = {
  url: string;
  method: string;
  headers: Headers;
  body: string | undefined;
  cache: RequestCache | undefined;
};
let upstream: Upstream[];
let events: BffSecurityEvent[] = [];
let handler: (call: Upstream) => Response | Promise<Response>;
const realFetch = globalThis.fetch;

const bff = createBff({
  app: "web",
  apiUrl: "http://api:8000",
  allowedOrigins: [ORIGIN],
  bffSecret: SECRET,
  clientIp: (headers) => headers.get("x-real-ip"),
  refreshMaxAgeSeconds: 30 * 24 * 3600,
  loginPath: "/connexion",
  onSecurityEvent: (event) => events.push(event),
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
  events = [];
  handler = () => jsonResponse(200, { ok: true });
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const call: Upstream = {
      url: String(input),
      method: init?.method ?? "GET",
      headers: new Headers(init?.headers),
      body: typeof init?.body === "string" ? init.body : undefined,
      cache: init?.cache,
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
    rawBody?: string;
    cookies?: Record<string, string>;
    cookieHeader?: string;
    headers?: Record<string, string>;
  } = {},
): Request {
  const method = options.method ?? "GET";
  const hasBody = options.body !== undefined || options.rawBody !== undefined;
  const headers: Record<string, string> = {
    "X-Requested-With": "jeflink",
    "x-real-ip": "41.82.1.2",
    ...(method === "GET" ? {} : { Origin: ORIGIN }),
    ...(hasBody ? { "Content-Type": "application/json" } : {}),
    ...options.headers,
  };
  const jar = { [COOKIES.device]: DEVICE, ...options.cookies };
  headers.cookie =
    options.cookieHeader ??
    Object.entries(jar)
      .map(([name, value]) => `${name}=${value}`)
      .join("; ");
  return new Request(`${ORIGIN}${path}`, {
    method,
    headers,
    ...(options.body !== undefined ? { body: JSON.stringify(options.body) } : {}),
    ...(options.rawBody !== undefined ? { body: options.rawBody } : {}),
  });
}

function setCookies(response: Response): string[] {
  return response.headers.getSetCookie();
}

function cookieNamed(response: Response, name: string): string | undefined {
  return setCookies(response).find((c) => c.startsWith(`${name}=`));
}

const authenticated = {
  status: "authenticated",
  user: { public_id: "u" },
  tokens: {
    access: "ACC",
    refresh: "jfr_REF",
    access_expires_at: new Date(Date.now() + 900_000).toISOString(),
  },
};

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

  it("X-Requested-With exigé, sauf pour la page de rebond du refresh", async () => {
    const response = await bff.handle(browser("/api/me/", { headers: { "X-Requested-With": "" } }));
    assert.equal(response.status, 403);
    const navigation = new Request(`${ORIGIN}/api/auth/token/refresh/?next=/compte`);
    assert.equal((await bff.handle(navigation)).status, 200);
  });

  it("JSON imposé dès qu'il y a un corps", async () => {
    const response = await bff.handle(
      browser("/api/me/", {
        method: "PATCH",
        rawBody: "nom=x",
        headers: { "Content-Type": "text/plain" },
      }),
    );
    assert.equal(response.status, 415);
    assert.equal(upstream.length, 0);
  });

  it("POST et DELETE sans corps acceptés, sans Content-Type (I4)", async () => {
    handler = () => new Response(null, { status: 204 });
    const deleted = await bff.handle(browser("/api/me/sessions/abc/", { method: "DELETE" }));
    assert.equal(deleted.status, 204);
    assert.equal(upstream[0]?.method, "DELETE");
    assert.equal(upstream[0]?.body, undefined);
    assert.equal(upstream[0]?.headers.get("content-type"), null);
    const posted = await bff.handle(browser("/api/me/invitations/x/decline/", { method: "POST" }));
    assert.equal(posted.status, 204);
  });

  it("corps plafonné à 64 Kio, même sans Content-Length (I8)", async () => {
    const big = new TextEncoder().encode(`{"a":"${"x".repeat(70 * 1024)}"}`);
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        for (let i = 0; i < big.length; i += 8192) controller.enqueue(big.slice(i, i + 8192));
        controller.close();
      },
    });
    const request = new Request(`${ORIGIN}/api/me/`, {
      method: "PATCH",
      headers: {
        Origin: ORIGIN,
        "X-Requested-With": "jeflink",
        "Content-Type": "application/json",
      },
      body: stream,
      duplex: "half",
    } as RequestInit);
    const response = await bff.handle(request);
    assert.equal(response.status, 413);
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
      "/api/Internal/x",
      "/api/SCHEMA",
      "/api/docs",
      "/api/%2e%2e/admin/",
      "/api/me%2fsessions/",
      "/api/me/..%2f..%2fadmin",
      "/api/auth/inconnu/",
      "/api/AUTH/token/refresh/",
    ]) {
      const response = await bff.handle(browser(path));
      assert.ok([404, 405].includes(response.status), `${path} → ${response.status}`);
    }
    assert.equal(upstream.length, 0);
  });

  it("safeApiPath refuse encodages, antislash, doubles barres et préfixes interdits", () => {
    for (const path of [
      "/api/%2E%2E/x",
      "/api/a%2fb",
      "/api/a%5cb",
      "/api/a\\b",
      "/api//x",
      "/api/../x",
      "/admin/",
      "http://x/api/",
      "/api/internal",
      "/api/Webhooks/x",
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
    assert.equal(call?.headers.get("x-install-id"), DEVICE);
    assert.equal(call?.headers.get("accept-language"), "wo");
    assert.equal(call?.headers.get("x-forwarded-for"), null);
    assert.equal(call?.headers.get("cookie"), null);
  });

  it("IP cliente invalide ignorée (M7)", async () => {
    await bff.handle(browser("/api/me/", { headers: { "x-real-ip": "1.2.3.4, 5.6.7.8" } }));
    assert.equal(upstream[0]?.headers.get("x-jeflink-client-ip"), null);
  });

  it("identifiant d'appareil non UUID régénéré (M6)", async () => {
    const response = await bff.handle(
      browser("/api/me/", { cookies: { [COOKIES.device]: "forge" } }),
    );
    const sent = upstream[0]?.headers.get("x-install-id") ?? "";
    assert.notEqual(sent, "forge");
    assert.match(sent, /^[0-9a-f-]{36}$/);
    assert.ok(cookieNamed(response, COOKIES.device)?.startsWith(`${COOKIES.device}=${sent}`));
  });

  it("Set-Cookie de Django jamais transmis ; en-têtes de cache et nosniff partout", async () => {
    handler = () => jsonResponse(200, { ok: 1 }, { "Set-Cookie": "sessionid=django" });
    const response = await bff.handle(browser("/api/me/"));
    assert.ok(!setCookies(response).some((c) => c.startsWith("sessionid")));
    assert.equal(response.headers.get("cache-control"), "private, no-store");
    assert.equal(response.headers.get("vary"), "Cookie, Authorization");
    assert.equal(response.headers.get("x-content-type-options"), "nosniff");
  });

  it("corps non JSON d'amont rendu en texte brut, redirection d'amont refusée", async () => {
    handler = () =>
      new Response("<script>alert(1)</script>", {
        status: 502,
        headers: { "Content-Type": "text/html" },
      });
    const html = await bff.handle(browser("/api/me/"));
    assert.equal(html.headers.get("content-type"), "text/plain; charset=utf-8");
    handler = () => new Response(null, { status: 301, headers: { Location: "https://evil.test" } });
    const moved = await bff.handle(browser("/api/me"));
    assert.equal(moved.status, 502);
    assert.equal(moved.headers.get("location"), null);
  });

  it("proxy : un jeton est masqué et signalé, la réponse passe (M1, I-A)", async () => {
    for (const body of [
      { data: { items: [{ note: FAKE_REFRESH }] } },
      { autre: `avant ${FAKE_JWT} après` },
    ]) {
      handler = () => jsonResponse(200, body);
      const response = await bff.handle(browser("/api/me/"));
      assert.equal(response.status, 200);
      const text = await response.text();
      assert.ok(!text.includes(FAKE_REFRESH) && !text.includes(FAKE_JWT), text);
      assert.ok(text.includes("[jeton masqué]"));
      JSON.parse(text); // toujours du JSON valide
    }
    handler = () => new Response(`erreur ${FAKE_REFRESH}`, { status: 500 });
    const plain = await bff.handle(browser("/api/me/"));
    assert.ok(!(await plain.text()).includes(FAKE_REFRESH));
    assert.equal(events.length, 3);
    assert.ok(events.every((e) => e.kind === "token_leak_masked" && e.path === "/api/me/"));
    assert.ok(!JSON.stringify(events).includes("xxxxxxxx"));
  });

  it("proxy : jeton caché derrière un échappement JSON masqué aussi (contre-revue, m-1)", async () => {
    for (const prefix of ["note\n", "a\t", "\u0001", "é"]) {
      handler = () =>
        new Response(JSON.stringify({ d: `${prefix}${FAKE_REFRESH}` }).replace("é", "\\u00e9"), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      const response = await bff.handle(browser("/api/me/"));
      const text = await response.text();
      assert.ok(!text.includes("x".repeat(43)), JSON.stringify(prefix));
      assert.equal(JSON.parse(text).d, `${prefix}[jeton masqué]`);
    }
    handler = () => jsonResponse(400, { code: "x", detail: `ligne\n${FAKE_REFRESH}` });
    const refused = await bff.handle(
      browser("/api/auth/otp/verify/", { method: "POST", body: { code: "1" } }),
    );
    assert.equal(refused.status, 502);
  });

  it("proxy : une clé __proto__ reste une donnée après masquage", async () => {
    handler = () =>
      new Response(`{"__proto__":{"x":"${FAKE_REFRESH}"},"y":1}`, {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    const response = await bff.handle(browser("/api/me/"));
    const body = JSON.parse(await response.text());
    assert.deepEqual(Object.keys(body), ["__proto__", "y"]);
  });

  it("proxy : aucun faux positif sur un texte d'utilisateur ni sur des clés usuelles (I-A)", async () => {
    const body = {
      description: "voir dossier jfr_2026_10_01_cuisine",
      access: "Code du portail : 1234",
      refresh: 30,
      tokens: 3,
    };
    handler = () => jsonResponse(200, body);
    const response = await bff.handle(browser("/api/missions/"));
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), body);
    assert.equal(events.length, 0);
  });
});

describe("jetons en cookies", () => {
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
    const access = cookieNamed(response, COOKIES.access);
    assert.ok(
      access?.startsWith(`${COOKIES.access}=ACC`) &&
        access.includes("HttpOnly") &&
        access.includes("Secure"),
    );
    const refresh = cookieNamed(response, COOKIES.refresh);
    assert.ok(refresh?.includes("Path=/api/auth") && refresh.includes("SameSite=Strict"));
    const witness = cookieNamed(response, COOKIES.session);
    assert.ok(witness?.startsWith(`${COOKIES.session}=1`) && witness.includes("Path=/;"));
    const sent = JSON.parse(upstream[0]?.body ?? "{}");
    assert.equal(sent.app, undefined);
    assert.deepEqual(sent.device, { platform: "web", install_id: DEVICE, label: "Chrome" });
  });

  it("cookie d'accès : durée de vie moins la marge, jamais sous 60 s (M4)", async () => {
    handler = () =>
      jsonResponse(200, {
        ...authenticated,
        tokens: { ...authenticated.tokens, access_expires_at: new Date().toISOString() },
      });
    const response = await bff.handle(
      browser("/api/auth/otp/verify/", { method: "POST", body: { code: "1" } }),
    );
    assert.ok(cookieNamed(response, COOKIES.access)?.includes("Max-Age=60"));
  });

  it("erreur d'un endpoint de jetons : Retry-After transmis, aucune fuite (M1, M10)", async () => {
    handler = () => jsonResponse(429, { code: "throttled" }, { "Retry-After": "30" });
    const throttled = await bff.handle(
      browser("/api/auth/otp/verify/", { method: "POST", body: { code: "1" } }),
    );
    assert.equal(throttled.status, 429);
    assert.equal(throttled.headers.get("retry-after"), "30");
    handler = () => jsonResponse(400, { code: "x", detail: FAKE_REFRESH });
    const leaked = await bff.handle(
      browser("/api/auth/otp/verify/", { method: "POST", body: { code: "1" } }),
    );
    assert.equal(leaked.status, 502);
    assert.deepEqual(events, [
      { kind: "token_leak_refused", path: "/api/auth/otp/verify/", status: 400 },
    ]);
  });

  it("jeton résiduel dans un corps de jetons : 502, aucun cookie posé", async () => {
    handler = () => jsonResponse(200, { ...authenticated, debug: FAKE_JWT });
    const response = await bff.handle(
      browser("/api/auth/otp/verify/", { method: "POST", body: { code: "1" } }),
    );
    assert.equal(response.status, 502);
    assert.equal(cookieNamed(response, COOKIES.access), undefined);
  });

  it("parcours Ops : jeton MFA en cookie, jamais dans le corps", async () => {
    handler = () => jsonResponse(200, { status: "mfa_required", mfa_token: "jfm_SECRET" });
    const first = await bff.handle(
      browser("/api/auth/otp/verify/", { method: "POST", body: { code: "1" } }),
    );
    assert.deepEqual(await first.json(), { status: "mfa_required" });
    assert.ok(cookieNamed(first, COOKIES.mfa)?.includes("Max-Age=300"));
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

  it("step-up : réponse de forme inattendue refusée (M9)", async () => {
    handler = () => jsonResponse(200, { access: 1 });
    const response = await bff.handle(
      browser("/api/auth/mfa/totp/step-up/", {
        method: "POST",
        body: { code: "111111" },
        cookies: { [COOKIES.access]: "A" },
      }),
    );
    assert.equal(response.status, 502);
    assert.equal(cookieNamed(response, COOKIES.access), undefined);
  });

  it("fresh-start sans corps : nouveaux cookies", async () => {
    handler = () => jsonResponse(200, authenticated);
    const response = await bff.handle(
      browser("/api/me/fresh-start/", { method: "POST", cookies: { [COOKIES.access]: "A" } }),
    );
    assert.equal(response.status, 200);
    assert.ok(cookieNamed(response, COOKIES.refresh)?.startsWith(`${COOKIES.refresh}=jfr_REF`));
  });
});

/** Exécute le script de la page de rebond dans un bac à sable : stockages, fetch et navigation. */
async function runBounce(
  storage: { local: Map<string, string>; session: Map<string, string> },
  status = 200,
): Promise<{ posts: number; went: string[] }> {
  const page = await bff.handle(new Request(`${ORIGIN}/api/auth/token/refresh/?next=/compte`));
  const script = /<script nonce="[^"]+">([\s\S]*?)<\/script>/.exec(await page.text())?.[1] ?? "";
  const store = (map: Map<string, string>) => ({
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => void map.set(key, value),
  });
  const result = { posts: 0, went: [] as string[] };
  runInNewContext(script, {
    localStorage: store(storage.local),
    sessionStorage: store(storage.session),
    location: { replace: (url: string) => result.went.push(url) },
    navigator: {},
    fetch: async () => {
      result.posts += 1;
      return { ok: status === 200, status };
    },
    AbortController,
    setTimeout: () => 0, // délais neutralisés : le test ne doit pas attendre 20 s
    Date,
    String,
    Promise,
  });
  await new Promise((resolve) => setTimeout(resolve, 10));
  return result;
}

describe("page de rebond exécutée (contre-revue, I-1)", () => {
  it("sans marque : vrai refresh, marque posée, retour à next", async () => {
    const storage = { local: new Map<string, string>(), session: new Map<string, string>() };
    const run = await runBounce(storage);
    assert.equal(run.posts, 1);
    assert.deepEqual(run.went, ["/compte"]);
    assert.ok(storage.local.has("jf-refreshed-at"));
  });

  it("marque dans le futur (horloge corrigée en arrière) : vrai refresh, jamais de boucle", async () => {
    const storage = {
      local: new Map([["jf-refreshed-at", String(Date.now() + 3_600_000)]]),
      session: new Map<string, string>(),
    };
    assert.equal((await runBounce(storage)).posts, 1);
    // La marque est réécrite au présent : l'horloge ne peut plus bloquer les refresh suivants.
    assert.ok(Number(storage.local.get("jf-refreshed-at")) <= Date.now());
  });

  it("marque récente : sautée une seule fois par onglet, puis vrai refresh", async () => {
    const storage = {
      local: new Map([["jf-refreshed-at", String(Date.now() - 2_000)]]),
      session: new Map<string, string>(),
    };
    const first = await runBounce(storage);
    assert.equal(first.posts, 0);
    assert.deepEqual(first.went, ["/compte"]);
    const second = await runBounce(storage);
    assert.equal(second.posts, 1);
  });

  it("401 : connexion ; 503 : connexion avec raison=indisponible", async () => {
    const empty = () => ({ local: new Map<string, string>(), session: new Map<string, string>() });
    assert.deepEqual((await runBounce(empty(), 401)).went, ["/connexion?next=%2Fcompte"]);
    assert.deepEqual((await runBounce(empty(), 503)).went, [
      "/connexion?next=%2Fcompte&raison=indisponible",
    ]);
  });
});

describe("refresh", () => {
  const rotated = () =>
    jsonResponse(200, {
      access: "A2",
      refresh: "jfr_R2",
      access_expires_at: new Date(Date.now() + 900_000).toISOString(),
    });

  function postRefresh(cookies: Record<string, string>, cookieHeader?: string): Promise<Response> {
    return bff.handle(
      browser("/api/auth/token/refresh/", {
        method: "POST",
        cookies,
        ...(cookieHeader ? { cookieHeader } : {}),
      }),
    );
  }

  it("succès : refresh et témoin posés, jetons absents du corps", async () => {
    handler = rotated;
    const ok = await postRefresh({ [COOKIES.refresh]: "jfr_R1" });
    assert.equal(ok.status, 200);
    assert.equal(JSON.parse(upstream[0]?.body ?? "{}").refresh, "jfr_R1");
    assert.ok(cookieNamed(ok, COOKIES.refresh)?.startsWith(`${COOKIES.refresh}=jfr_R2`));
    assert.ok(cookieNamed(ok, COOKIES.session)?.startsWith(`${COOKIES.session}=1`));
    assert.equal((await ok.json()).refresh, undefined);
  });

  it("401 de Django : session effacée ; 429 : rien d'effacé, Retry-After transmis", async () => {
    handler = () => jsonResponse(401, { code: "session_revoked" });
    const gone = await postRefresh({ [COOKIES.refresh]: "jfr_R2" });
    assert.ok(cookieNamed(gone, COOKIES.refresh)?.includes("Max-Age=0"));
    assert.ok(cookieNamed(gone, COOKIES.session)?.includes("Max-Age=0"));

    handler = () => jsonResponse(429, { code: "throttled" }, { "Retry-After": "12" });
    const busy = await postRefresh({ [COOKIES.refresh]: "jfr_R2" });
    assert.equal(busy.status, 429);
    assert.equal(busy.headers.get("retry-after"), "12");
    assert.equal(cookieNamed(busy, COOKIES.refresh), undefined);
  });

  it("refresh absent : 401 sans effacer l'accès, témoin seul effacé (I3, M2)", async () => {
    const response = await postRefresh({ [COOKIES.access]: "A", [COOKIES.session]: "1" });
    assert.equal(response.status, 401);
    assert.equal(cookieNamed(response, COOKIES.access), undefined);
    assert.ok(cookieNamed(response, COOKIES.session)?.includes("Max-Age=0"));
    assert.equal(upstream.length, 0);
  });

  it("refresh en double : cookie du domaine parent effacé aussi, alerte (m1)", async () => {
    const withDomain = createBff({
      app: "web",
      apiUrl: "http://api:8000",
      allowedOrigins: [ORIGIN],
      bffSecret: SECRET,
      clientIp: () => null,
      refreshMaxAgeSeconds: 60,
      loginPath: "/connexion",
      cookieDomain: "jeflink.test",
      onSecurityEvent: (event) => events.push(event),
    });
    const response = await withDomain.handle(
      browser("/api/auth/token/refresh/", {
        method: "POST",
        cookieHeader: `${COOKIES.refresh}=jfr_A; ${COOKIES.refresh}=jfr_B`,
      }),
    );
    assert.equal(response.status, 401);
    const cleared = setCookies(response).filter((c) => c.startsWith(`${COOKIES.refresh}=;`));
    // Hôte + domaine parent sur chaque chemin qui atteint le refresh (contre-revue, m-2).
    const parent = cleared.filter((c) => c.includes("Domain=jeflink.test"));
    assert.equal(cleared.length, 1 + parent.length);
    for (const path of ["/", "/api/auth", "/api/auth/token/refresh/"]) {
      assert.ok(
        parent.some((c) => c.includes(`Path=${path};`)),
        path,
      );
    }
    assert.deepEqual(events, [{ kind: "duplicate_refresh", path: "/api/auth/token/refresh/" }]);
  });

  it("refresh en double (fixation par un sous-domaine) : refusé et effacé (M5)", async () => {
    const response = await postRefresh(
      {},
      `${COOKIES.device}=${DEVICE}; ${COOKIES.refresh}=jfr_A; ${COOKIES.refresh}=jfr_B`,
    );
    assert.equal(response.status, 401);
    assert.ok(cookieNamed(response, COOKIES.refresh)?.includes("Max-Age=0"));
    assert.equal(upstream.length, 0);
  });

  it("GET : page de rebond sans changement d'état, next validé (I2, C1)", async () => {
    const response = await bff.handle(
      new Request(`${ORIGIN}/api/auth/token/refresh/?next=/.//evil.test/x`, {
        headers: { cookie: `${COOKIES.refresh}=jfr_A` },
      }),
    );
    assert.equal(response.status, 200);
    assert.equal(upstream.length, 0);
    assert.ok(!setCookies(response).some((c) => c.startsWith(`${COOKIES.refresh}=`)));
    const csp = response.headers.get("content-security-policy") ?? "";
    const nonce = /'nonce-([^']+)'/.exec(csp)?.[1];
    assert.ok(nonce && csp.includes("default-src 'none'"));
    const html = await response.text();
    assert.ok(html.includes(`nonce="${nonce}"`));
    assert.ok(html.includes('"next":"/"'));
    assert.ok(html.includes('"lock":"jf-refresh"'));
    // Délais et repli (I-D) : verrou et POST bornés, meta refresh hors noscript.
    assert.ok(html.includes('"fetchTimeout":20000') && html.includes('"lockTimeout":30000'));
    assert.ok(html.includes('"mark":"jf-refreshed-at"'));
    assert.match(
      html,
      /<meta http-equiv="refresh" content="60;url=\/connexion\?next=%2F&amp;raison=indisponible">/,
    );
    assert.ok(!html.includes("evil.test"));
  });

  it("page de rebond : aucune injection possible par next", async () => {
    const response = await bff.handle(
      new Request(
        `${ORIGIN}/api/auth/token/refresh/?next=${encodeURIComponent('/a"</script><script>x()')}`,
      ),
    );
    const html = await response.text();
    assert.ok(!html.includes("</script><script>x()"));
  });

  it("refreshRedirectPath n'accepte qu'un chemin interne", () => {
    assert.equal(bff.refreshRedirectPath("//evil.test"), "/api/auth/token/refresh/?next=%2F");
    assert.equal(bff.refreshRedirectPath("/compte"), "/api/auth/token/refresh/?next=%2Fcompte");
  });
});

describe("déconnexion", () => {
  it("révoque par le refresh même sans accès (I5), cookies effacés, appareil gardé", async () => {
    handler = () => new Response(null, { status: 204 });
    const response = await bff.handle(
      browser("/api/auth/logout/", { method: "POST", cookies: { [COOKIES.refresh]: "jfr_R" } }),
    );
    assert.equal(response.status, 204);
    assert.equal(upstream.length, 1);
    assert.equal(upstream[0]?.url, "http://api:8000/api/auth/token/revoke/");
    assert.equal(JSON.parse(upstream[0]?.body ?? "{}").refresh, "jfr_R");
    for (const name of [COOKIES.access, COOKIES.refresh, COOKIES.session, COOKIES.mfa]) {
      assert.ok(cookieNamed(response, name)?.includes("Max-Age=0"), name);
    }
    assert.equal(cookieNamed(response, COOKIES.device), undefined);
  });

  it("avec accès : Django prévenu aussi par l'accès ; panne de Django sans effet", async () => {
    handler = () => {
      throw new Error("réseau coupé");
    };
    const response = await bff.handle(
      browser("/api/auth/logout/", {
        method: "POST",
        cookies: { [COOKIES.access]: "ACC", [COOKIES.refresh]: "jfr_R" },
      }),
    );
    assert.equal(response.status, 204);
    assert.equal(upstream.length, 2);
    assert.ok(upstream.some((c) => c.headers.get("authorization") === "Bearer ACC"));
    assert.deepEqual(events, [{ kind: "revoke_failed", path: "/api/auth/token/revoke/" }]);
    assert.ok(cookieNamed(response, COOKIES.access)?.includes("Max-Age=0"));
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
      bff.handle(browser("/api/me/", { cookies: { [COOKIES.access]: "A" } })),
      bff.handle(browser("/api/me/", { cookies: { [COOKIES.access]: "B" } })),
    ]);
    assert.deepEqual(await a.json(), { vu: "Bearer A" });
    assert.deepEqual(await b.json(), { vu: "Bearer B" });
  });
});

describe("contexte serveur (I6)", () => {
  it("transport fermé : jeton de la requête, no-store, rien de secret lisible", async () => {
    const server = bff.server(
      browser("/compte", {
        cookies: { [COOKIES.access]: "SRV" },
        headers: { "Accept-Language": "wo" },
      }),
    );
    assert.equal(server.needsRefresh, false);
    const serialized = JSON.stringify(server);
    assert.ok(!serialized.includes("SRV") && !serialized.includes(SECRET));
    assert.deepEqual(Object.keys(server.options), ["transport"]);
    await jeflinkFetch("/api/me/?x=1", server.options);
    const [call] = upstream;
    assert.equal(call?.url, "http://api:8000/api/me/?x=1");
    assert.equal(call?.headers.get("authorization"), "Bearer SRV");
    assert.equal(call?.headers.get("x-jeflink-bff"), SECRET);
    assert.equal(call?.headers.get("x-install-id"), DEVICE);
    assert.equal(call?.headers.get("accept-language"), "wo");
    assert.equal(call?.cache, "no-store");
  });

  it("transport : endpoints de jetons et chemins dangereux refusés", async () => {
    const server = bff.server(browser("/compte", { cookies: { [COOKIES.access]: "SRV" } }));
    for (const path of [
      "/api/auth/token/refresh/",
      "/api/auth/otp/verify/",
      "/api/me/fresh-start/",
      "/api/internal/x",
      "https://evil.test/api/me/",
      "//evil.test/api/me/",
      "/api/%2e%2e/admin/",
    ]) {
      await assert.rejects(server.options.transport(path, {}), Error, path);
    }
    assert.equal(upstream.length, 0);
    await server.options.transport("/api/auth/config/", {});
    assert.equal(upstream.length, 1);
  });

  it("accepte les en-têtes d'un Server Component (m7)", async () => {
    const incoming = new Headers({
      cookie: `${COOKIES.access}=SRV; ${COOKIES.device}=${DEVICE}`,
      "x-real-ip": "41.82.1.2",
    });
    const server = bff.server(incoming);
    await jeflinkFetch("/api/me/", server.options);
    assert.equal(upstream[0]?.headers.get("authorization"), "Bearer SRV");
    assert.equal(upstream[0]?.headers.get("x-jeflink-client-ip"), "41.82.1.2");
  });

  it("transport : paramètre de chemin piégé refusé avant normalisation (I-C)", async () => {
    const server = bff.server(browser("/compte", { cookies: { [COOKIES.access]: "SRV" } }));
    for (const path of [
      "/api/ops/accounts/../../me/sessions/revoke-others/",
      "/api/ops/accounts/..%2F..%2Fme%2F/",
      "/api/ops/accounts/./x/",
    ]) {
      await assert.rejects(server.options.transport(path, {}), Error, path);
    }
    assert.equal(upstream.length, 0);
  });

  it("needsRefresh : témoin de session sans accès (I1)", () => {
    // Une page ne reçoit jamais le refresh (Path=/api/auth) : seul le témoin la renseigne.
    const expired = bff.server(browser("/compte", { cookies: { [COOKIES.session]: "1" } }));
    assert.equal(expired.needsRefresh, true);
    const anonymous = bff.server(browser("/compte"));
    assert.equal(anonymous.needsRefresh, false);
  });
});

describe("safeNextPath (S20, C1)", () => {
  it("chemin relatif interne seulement, contrôlé après normalisation", () => {
    for (const bad of [
      "https://evil.test",
      "//evil.test",
      "/\\evil.test",
      "javascript:alert(1)",
      "compte",
      "/a\nb",
      "/.//evil.test",
      "/a/..//evil.test/x",
      "/%2e//evil.test",
      "/..//evil.test",
      "/./\\evil.test",
      "/api/auth/token/refresh/?next=/x",
      "/API/me/",
    ]) {
      assert.equal(safeNextPath(bad), "/", bad);
    }
    assert.equal(safeNextPath("/compte?onglet=2#x"), "/compte?onglet=2#x");
    assert.equal(safeNextPath("/apiculture"), "/apiculture");
    // Caractère non réservé encodé : `/%61pi/` est `/api/` (m6).
    assert.equal(safeNextPath("/%61pi/auth/token/refresh/?next=/x"), "/");
  });
});

describe("configuration", () => {
  const valid = {
    app: "web" as const,
    apiUrl: "http://api:8000",
    allowedOrigins: [ORIGIN],
    bffSecret: SECRET,
    clientIp: () => null,
    refreshMaxAgeSeconds: 1,
    loginPath: "/connexion",
  } satisfies BffConfig;

  it("refuse une configuration dangereuse", () => {
    for (const override of [
      { allowedOrigins: [] },
      { allowedOrigins: ["https://jeflink.test/"] },
      { bffSecret: "court" },
      { apiUrl: "http://api:8000/chemin" },
      { loginPath: "//evil.test" },
      { loginPath: "/connexion?x=1" },
      { refreshMaxAgeSeconds: 0 },
      { cookieDomain: ".jeflink.test" },
      { cookieDomain: "jeflink.test; Secure" },
    ]) {
      assert.throws(() => createBff({ ...valid, ...override }), JSON.stringify(override));
    }
    assert.doesNotThrow(() => createBff(valid));
  });
});
