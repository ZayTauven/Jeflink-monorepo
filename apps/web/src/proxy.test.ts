// Tests du proxy des pages (spec 001, web 1 ; revue web 1, I-3) : matcher, CSP à nonce,
// x-jf-path, cache des pages avec session, barre finale.
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { unstable_doesMiddlewareMatch } from "next/experimental/testing/server";
import { NextRequest } from "next/server";

import { PATH_HEADER } from "./lib/routes.ts";
import { canonicalPath, config, proxy } from "./proxy.ts";

const ORIGIN = "https://jeflink.sn";

function call(path: string, headers: Record<string, string> = {}) {
  return proxy(new NextRequest(`${ORIGIN}${path}`, { headers }));
}

/** En-têtes de requête transmis à la page par NextResponse.next({ request }). */
function forwarded(response: Response, name: string): string | null {
  return response.headers.get(`x-middleware-request-${name}`);
}

describe("matcher", () => {
  const matches = (path: string) =>
    unstable_doesMiddlewareMatch({ config, url: `${ORIGIN}${path}` });

  for (const path of ["/api/me/", "/api/auth/token/refresh/", "/api", "/_next/static/a.js"]) {
    it(`exclut ${path} (le BFF a ses propres règles)`, () => {
      assert.equal(matches(path), false);
    });
  }

  for (const path of ["/favicon.ico", "/robots.txt", "/sitemap.xml"]) {
    it(`exclut le fichier ${path}`, () => {
      assert.equal(matches(path), false);
    });
  }

  for (const path of [
    "/",
    "/connexion",
    "/plombier/ouakam",
    "/robots.txt-x/ouakam",
    "/apiculteur",
  ]) {
    it(`couvre la page ${path}`, () => {
      assert.equal(matches(path), true);
    });
  }
});

describe("proxy", () => {
  it("CSP à nonce, neuve à chaque requête, transmise à Next et au navigateur", () => {
    const first = call("/");
    const second = call("/");
    const csp = first.headers.get("content-security-policy") ?? "";
    const nonce = /'nonce-([^']+)'/.exec(csp)?.[1];
    assert.ok(nonce && nonce.length >= 22);
    assert.notEqual(csp, second.headers.get("content-security-policy"));
    assert.equal(forwarded(first, "content-security-policy"), csp);
    for (const directive of [
      "frame-ancestors 'none'",
      "object-src 'none'",
      "base-uri 'self'",
      "form-action 'self'",
      `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`,
    ]) {
      assert.ok(csp.includes(directive), directive);
    }
    assert.ok(!csp.includes("unsafe-inline"));
  });

  it("x-jf-path est posé par le proxy, jamais repris du navigateur", () => {
    const response = call("/compte?onglet=2", { [PATH_HEADER]: "//evil.example/x" });
    assert.equal(forwarded(response, PATH_HEADER), "/compte?onglet=2");
  });

  it("page sans session : le cache reste décidé par Next", () => {
    assert.equal(call("/").headers.get("cache-control"), null);
  });

  for (const cookie of ["__Host-jf_at=a", "__Host-jf_sess=1"]) {
    it(`page avec ${cookie.split("=")[0]} : private, no-store`, () => {
      const response = call("/compte", { cookie });
      assert.equal(response.headers.get("cache-control"), "private, no-store");
    });
  }

  it("barre finale : 308 vers la forme sans barre, requête gardée, même origine", () => {
    const response = call("/a/?q=1");
    assert.equal(response.status, 308);
    const location = new URL(response.headers.get("location") ?? "", ORIGIN);
    assert.equal(location.origin, ORIGIN);
    assert.equal(`${location.pathname}${location.search}`, "/a?q=1");
  });

  it("majuscules : 308 vers les minuscules, requête intacte (valeurs comprises)", () => {
    const response = call("/Plombier/Ouakam?Quartier=PA&next=%2FCompte");
    assert.equal(response.status, 308);
    const location = new URL(response.headers.get("location") ?? "", ORIGIN);
    assert.equal(location.origin, ORIGIN);
    assert.equal(location.pathname, "/plombier/ouakam");
    assert.equal(location.search, "?Quartier=PA&next=%2FCompte");
  });

  it("majuscules et barre finale : un seul 308 vers la forme unique", () => {
    const response = call("/Plombier/Ouakam/");
    assert.equal(response.status, 308);
    assert.equal(new URL(response.headers.get("location") ?? "").pathname, "/plombier/ouakam");
  });

  it("une page déjà en minuscules n'est pas redirigée", () => {
    assert.equal(call("/plombier/ouakam").status, 200);
    assert.equal(call("/").status, 200);
  });

  it("canonicalPath garde les séquences %XX telles quelles (pas de boucle)", () => {
    assert.equal(canonicalPath("/sacr%C3%A9-c%C5%93ur"), "/sacr%C3%A9-c%C5%93ur");
    assert.equal(canonicalPath("/Sacr%C3%A9"), "/sacr%C3%A9");
    assert.equal(canonicalPath("/"), "/");
  });

  it("/api n'est jamais touché : hors du matcher", () => {
    assert.equal(unstable_doesMiddlewareMatch({ config, url: `${ORIGIN}/api/Me/` }), false);
  });

  for (const path of ["//evil.example/x/", "/\\evil.example/", "/%2F%2Fevil.example/"]) {
    it(`${path} : jamais de redirection vers un autre hôte`, () => {
      const response = call(path);
      const location = response.headers.get("location");
      if (location) assert.equal(new URL(location, ORIGIN).origin, ORIGIN);
    });
  }
});

describe("proxy : stockage des photos", () => {
  it("img-src autorise l'origine du stockage, et elle seule", () => {
    const csp = call("/").headers.get("content-security-policy") ?? "";
    // Test lancé en NODE_ENV=test : sans variable, aucune origine ajoutée.
    assert.ok(/img-src 'self' blob: data:(;| |$)/.test(csp));
  });
});
