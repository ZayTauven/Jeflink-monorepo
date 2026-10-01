// Tests des en-têtes de next.config.ts (spec 001, web 1 ; revue web 1, I-3).
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { unstable_getResponseFromNextConfig } from "next/experimental/testing/server";

import nextConfig from "../next.config.ts";

async function headersOf(path: string): Promise<Headers> {
  const response = await unstable_getResponseFromNextConfig({
    url: `https://jeflink.sn${path}`,
    nextConfig,
  });
  return response.headers;
}

describe("next.config.ts", () => {
  for (const path of ["/connexion", "/connexion/code", "/connexion?next=%2Fcompte"]) {
    it(`${path} : Referrer-Policy same-origin (next ne part jamais vers un autre site)`, async () => {
      assert.equal((await headersOf(path)).get("referrer-policy"), "same-origin");
    });
  }

  it("ailleurs : strict-origin-when-cross-origin", async () => {
    assert.equal((await headersOf("/")).get("referrer-policy"), "strict-origin-when-cross-origin");
    assert.equal(
      (await headersOf("/connexion-pro")).get("referrer-policy"),
      "strict-origin-when-cross-origin",
    );
  });

  it("toutes les pages : HSTS hors dev, cadre interdit, nosniff", async () => {
    const headers = await headersOf("/plombier/ouakam");
    assert.equal(headers.get("strict-transport-security"), "max-age=31536000; includeSubDomains");
    assert.equal(headers.get("x-frame-options"), "DENY");
    assert.equal(headers.get("x-content-type-options"), "nosniff");
  });

  it("barre finale gardée pour /api (Django l'exige), aucun en-tête x-powered-by", () => {
    assert.equal(nextConfig.skipTrailingSlashRedirect, true);
    assert.equal(nextConfig.poweredByHeader, false);
  });

  it("aucune variable figée au build par next.config (env)", () => {
    assert.equal(nextConfig.env, undefined);
  });
});
