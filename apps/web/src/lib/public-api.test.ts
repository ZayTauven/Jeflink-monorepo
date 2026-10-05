// Tests de `publicApi()` (spec 006, web 2 [sécu]) : GET seulement, liste fermée de chemins et
// d'en-têtes, aucun cookie, jeton ni en-tête du visiteur, dernière copie en cas de panne, test
// d'architecture (aucun `serverApi` sous `app/(site)`).
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, it } from "node:test";

import {
  buildPublicRequest,
  checkPublicPath,
  createPublicTransport,
  isNotFoundError,
  PUBLIC_REQUEST_HEADERS,
  PublicApiRefusal,
} from "./public-api-core.ts";

const SETTINGS = { apiUrl: "http://api.internal", secret: "s".repeat(40), app: "web" };

function headerNames(headers: HeadersInit | undefined): string[] {
  return [...new Headers(headers).keys()].sort();
}

describe("buildPublicRequest : en-têtes", () => {
  const visitor = {
    method: "GET",
    headers: {
      Cookie: "__Host-jf_at=abc",
      Authorization: "Bearer jeton",
      "X-Jeflink-Client-Ip": "41.82.1.2",
      "X-Install-Id": "device",
      "X-Forwarded-For": "1.2.3.4",
      "X-Requested-With": "jeflink",
      "Accept-Language": "wo",
    },
  };

  it("liste fermée : exactement quatre en-têtes, ceux de l'appelant ignorés", () => {
    const { init } = buildPublicRequest("/api/catalog/trades/", visitor, SETTINGS);
    assert.deepEqual(
      headerNames(init.headers),
      [...PUBLIC_REQUEST_HEADERS].map((name) => name.toLowerCase()).sort(),
    );
    const headers = new Headers(init.headers);
    for (const forbidden of [
      "cookie",
      "authorization",
      "x-jeflink-client-ip",
      "x-install-id",
      "x-forwarded-for",
      "x-requested-with",
    ]) {
      assert.equal(headers.has(forbidden), false, forbidden);
    }
    assert.equal(headers.get("accept-language"), "fr", "langue fixe, jamais celle du visiteur");
    assert.equal(headers.get("x-jeflink-bff"), SETTINGS.secret);
    assert.equal(headers.get("x-jeflink-app"), "web");
  });

  it("aucun cookie : credentials omit ; cache 300 s avec l'étiquette du préfixe", () => {
    const catalog = buildPublicRequest("/api/catalog/trades/", {}, SETTINGS);
    assert.equal(catalog.init.credentials, "omit");
    assert.deepEqual(catalog.init.next, { revalidate: 300, tags: ["catalog"] });
    assert.deepEqual(buildPublicRequest("/api/zones/", {}, SETTINGS).init.next.tags, ["zones"]);
    assert.deepEqual(buildPublicRequest("/api/stats/?trade=a", {}, SETTINGS).init.next.tags, [
      "stats",
    ]);
  });

  it("URL : origine interne, chemin et requête gardés", () => {
    const { url } = buildPublicRequest("/api/zones/ouakam/?trade=plombier", {}, SETTINGS);
    assert.equal(url, "http://api.internal/api/zones/ouakam/?trade=plombier");
  });

  it("le secret n'apparaît ni dans l'URL ni dans l'erreur d'un refus", () => {
    const { url } = buildPublicRequest("/api/catalog/trades/", {}, SETTINGS);
    assert.ok(!url.includes(SETTINGS.secret));
    try {
      buildPublicRequest("/api/me/", {}, SETTINGS);
      assert.fail("refus attendu");
    } catch (error) {
      assert.ok(error instanceof PublicApiRefusal);
      assert.ok(!(error as Error).message.includes(SETTINGS.secret));
    }
  });
});

describe("buildPublicRequest : méthode et chemins", () => {
  for (const method of ["POST", "PUT", "PATCH", "DELETE", "post"]) {
    it(`${method} refusé`, () => {
      assert.throws(
        () => buildPublicRequest("/api/catalog/trades/", { method }, SETTINGS),
        PublicApiRefusal,
      );
    });
  }

  it("GET avec corps refusé", () => {
    assert.throws(
      () => buildPublicRequest("/api/catalog/trades/", { body: "{}" }, SETTINGS),
      PublicApiRefusal,
    );
  });

  for (const path of [
    "/api/me/",
    "/api/requests/",
    "/api/auth/token/refresh/",
    "/api/catalogue/",
    "/api/catalog",
    "/api/CATALOG/trades/",
    "/api/catalog/../me/",
    "/api/catalog/%2e%2e/me/",
    "/api/catalog//x/",
    "/api/zones/%2Fx/",
    "/api/stats/\\x",
    "https://evil.example/api/catalog/",
    "//evil.example/api/catalog/",
    "/health/",
    "",
  ]) {
    it(`chemin refusé : ${JSON.stringify(path)}`, () => {
      assert.throws(() => checkPublicPath(path), PublicApiRefusal);
    });
  }

  it("chemins permis", () => {
    for (const path of [
      "/api/catalog/trades/",
      "/api/catalog/trades/plombier/",
      "/api/catalog/coverage/",
      "/api/zones/",
      "/api/zones/ouakam/",
      "/api/stats/",
    ]) {
      assert.equal(checkPublicPath(path).path, path);
    }
  });
});

describe("createPublicTransport : dernière copie", () => {
  const ok = (body: string) =>
    new Response(body, { status: 200, headers: { "content-type": "application/json" } });

  it("sert la dernière copie bonne si l'API tombe (erreur réseau ou 5xx)", async () => {
    let mode: "ok" | "down" | "5xx" = "ok";
    const transport = createPublicTransport(SETTINGS, {
      fetchImpl: async () => {
        if (mode === "down") throw new TypeError("fetch failed");
        if (mode === "5xx") return new Response("bad gateway", { status: 502 });
        return ok('[{"slug":"plombier"}]');
      },
    });
    assert.equal((await transport("/api/catalog/trades/", {})).status, 200);
    for (mode of ["down", "5xx"] as const) {
      const stale = await transport("/api/catalog/trades/", {});
      assert.equal(stale.status, 200, mode);
      assert.equal(await stale.text(), '[{"slug":"plombier"}]');
      assert.equal(stale.headers.get("x-jeflink-stale"), "1");
    }
  });

  it("sans copie : l'erreur reste une erreur (jamais une page vide ni un 404)", async () => {
    const down = createPublicTransport(SETTINGS, {
      fetchImpl: async () => {
        throw new TypeError("fetch failed");
      },
    });
    await assert.rejects(() => down("/api/zones/", {}), TypeError);
    const bad = createPublicTransport(SETTINGS, {
      fetchImpl: async () => new Response("x", { status: 503 }),
    });
    assert.equal((await bad("/api/zones/", {})).status, 503);
  });

  it("un 404 est une vraie réponse : jamais remplacé par la copie", async () => {
    let calls = 0;
    const transport = createPublicTransport(SETTINGS, {
      fetchImpl: async () =>
        ++calls === 1 ? ok("{}") : new Response('{"code":"zone_not_found"}', { status: 404 }),
    });
    await transport("/api/zones/ouakam/", {});
    assert.equal((await transport("/api/zones/ouakam/", {})).status, 404);
  });

  it("la requête envoyée à Django suit la liste fermée", async () => {
    let seen: RequestInit | undefined;
    const transport = createPublicTransport(SETTINGS, {
      fetchImpl: async (_url, init) => {
        seen = init;
        return ok("[]");
      },
    });
    await transport("/api/catalog/trades/", {
      method: "GET",
      headers: { Cookie: "x=1", Authorization: "Bearer x" },
    });
    assert.deepEqual(
      headerNames(seen?.headers),
      [...PUBLIC_REQUEST_HEADERS].map((name) => name.toLowerCase()).sort(),
    );
  });
});

describe("isNotFoundError", () => {
  const apiError = (status: number, code?: string) =>
    Object.assign(new Error(code ?? `HTTP ${status}`), { name: "ApiError", status, code });

  it("404 avec un code d'absence seulement", () => {
    assert.equal(isNotFoundError(apiError(404, "trade_not_found")), true);
    assert.equal(isNotFoundError(apiError(404, "zone_not_found")), true);
  });

  it("une panne n'est jamais une absence", () => {
    for (const error of [
      apiError(404),
      apiError(404, "autre"),
      apiError(500, "trade_not_found"),
      apiError(429),
      apiError(502),
      new TypeError("fetch failed"),
      null,
    ]) {
      assert.equal(isNotFoundError(error), false);
    }
  });
});

// --- Test d'architecture : le site public ne touche ni la session ni les en-têtes du visiteur.

const SRC = new URL("../", import.meta.url);

function sources(dir: URL): string[] {
  const out: string[] = [];
  const root = dir.pathname.replace(/^\/([A-Za-z]:)/, "$1");
  const walk = (path: string) => {
    for (const name of readdirSync(path)) {
      const full = join(path, name);
      if (statSync(full).isDirectory()) walk(full);
      else if (/\.(ts|tsx)$/.test(name) && !/\.test\.ts$/.test(name)) out.push(full);
    }
  };
  walk(decodeURIComponent(root));
  return out;
}

/** Code sans commentaires : les explications peuvent citer `serverApi` sans l'importer. */
function code(file: string | URL): string {
  return readFileSync(file, "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}

describe("architecture : pages publiques", () => {
  const files = [
    ...sources(new URL("app/(site)/", SRC)),
    ...sources(new URL("components/site/", SRC)),
  ];

  it("des fichiers à contrôler existent", () => {
    assert.ok(files.length > 10);
  });

  it("aucun import de serverApi, serverApiWithSession ni de lib/bff", () => {
    for (const file of files) {
      const text = code(file);
      assert.doesNotMatch(text, /\bserverApi(WithSession)?\b/, file);
      assert.doesNotMatch(text, /from ["'](@\/lib\/bff|(\.\.?\/)+lib\/bff)(\.ts)?["']/, file);
    }
  });

  it("aucune lecture de cookies() ni de headers() du visiteur", () => {
    for (const file of files) {
      const text = code(file);
      assert.doesNotMatch(text, /from ["']next\/headers["']/, file);
    }
  });

  it("public-api ne lit ni cookies ni en-têtes de la requête", () => {
    for (const name of ["lib/public-api.ts", "lib/public-api-core.ts"]) {
      const text = code(new URL(name, SRC));
      assert.doesNotMatch(text, /next\/headers|\bcookies\(|\bheaders\(\)/, name);
    }
  });
});
