// Tests : le cookie de langue ne touche que l'espace client (ADR 0013).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

import { usesLocaleCookie } from "./locale-scope.ts";

describe("usesLocaleCookie", () => {
  it("espace client : oui", () => {
    for (const path of ["/compte", "/compte/demandes", "/connexion?next=%2Fdemande", "/demande", "/demande?metier=a"]) {
      assert.equal(usesLocaleCookie(path), true, path);
    }
  });

  it("site public, 404, sitemap, inconnu : non (français pour tous)", () => {
    for (const path of ["/", "/plombier", "/plombier/ouakam", "/a-propos", "/recherche?q=1", "/comptes", "/demandeur", "/x/compte", null, undefined, ""]) {
      assert.equal(usesLocaleCookie(path), false, String(path));
    }
  });
});

describe("architecture : la langue du site public", () => {
  it("request.ts ne lit le cookie que derrière usesLocaleCookie", () => {
    const text = readFileSync(new URL("./request.ts", import.meta.url), "utf8");
    assert.match(text, /usesLocaleCookie\(path\)\s*\?\s*\(await cookies\(\)\)/);
    assert.equal((text.match(/cookies\(\)/g) ?? []).length, 1);
  });
});
