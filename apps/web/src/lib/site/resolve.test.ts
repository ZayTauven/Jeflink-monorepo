// Tests de la résolution des segments d'URL (spec 006) : slug, alias égal, jamais un préfixe.
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { resolveSlug } from "./resolve.ts";

const trades = [
  { slug: "plombier", aliases: ["plomberie", "fuite", "robinet"], names: ["Plomberie"] },
  { slug: "electricien", aliases: ["electricite", "coupure"], names: ["Électricité"] },
];
const zones = [
  { slug: "parcelles-assainies", aliases: ["Parcelles", "PA", "Unité 15"] },
  { slug: "sacre-coeur", aliases: ["Sacré-Cœur 3"] },
];

describe("resolveSlug", () => {
  it("slug connu : sa page", () => {
    assert.deepEqual(resolveSlug("plombier", trades), { kind: "found", slug: "plombier" });
  });

  it("mot égal à un alias ou au nom : redirection vers le slug", () => {
    assert.deepEqual(resolveSlug("plomberie", trades), { kind: "alias", slug: "plombier" });
    assert.deepEqual(resolveSlug("electricite", trades), { kind: "alias", slug: "electricien" });
    assert.deepEqual(resolveSlug("parcelles", zones), { kind: "alias", slug: "parcelles-assainies" });
    assert.deepEqual(resolveSlug("pa", zones), { kind: "alias", slug: "parcelles-assainies" });
    assert.deepEqual(resolveSlug("unite-15", zones), { kind: "alias", slug: "parcelles-assainies" });
  });

  it("jamais sur un préfixe ni sur un mot approchant", () => {
    for (const word of ["plomb", "plombi", "elec", "fui", "parcel", "sacre"]) {
      assert.equal(resolveSlug(word, [...trades, ...zones]).kind, "unknown", word);
    }
  });

  it("inconnu, vide ou trop long : inconnu", () => {
    for (const word of ["", "gorée", "x".repeat(80)]) {
      assert.equal(resolveSlug(word, trades).kind, "unknown", word);
    }
  });
});
