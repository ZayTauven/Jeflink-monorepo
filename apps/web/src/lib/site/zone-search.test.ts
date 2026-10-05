// Tests de la recherche de quartier (spec 006, web 8) : les exemples du critère d'acceptation.
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { cleanQuery, searchZones } from "./zone-search.ts";

const zones = [
  { slug: "parcelles-assainies", name: "Parcelles Assainies", aliases: ["Parcelles", "PA", "Unité 15"] },
  { slug: "sacre-coeur", name: "Sacré-Cœur", aliases: ["Sacré-Cœur 3", "Sicap Sacré-Cœur"] },
  { slug: "sicap-liberte", name: "Sicap Liberté", aliases: ["Sicap"] },
  { slug: "grand-yoff", name: "Grand Yoff", aliases: ["Grand-Yoff"] },
  { slug: "grand-dakar", name: "Grand Dakar", aliases: [] },
  { slug: "rufisque", name: "Rufisque", aliases: [] },
];
const open = new Set(["parcelles-assainies", "sacre-coeur", "sicap-liberte", "grand-yoff", "grand-dakar"]);

const slugs = (outcome: ReturnType<typeof searchZones>) =>
  outcome.kind === "suggest" ? outcome.zones.map((zone) => zone.slug) : [];

describe("searchZones", () => {
  it("« Parcelles » et « PA » : égalité, donc la page du quartier", () => {
    for (const query of ["Parcelles", "PA", "pa", "Unité 15", "unite 15"]) {
      const outcome = searchZones(query, zones, open);
      assert.equal(outcome.kind, "exact", query);
      if (outcome.kind === "exact") assert.equal(outcome.zone.slug, "parcelles-assainies");
    }
  });

  it("« Sacré-Cœur 3 » : égalité avec l'alias", () => {
    const outcome = searchZones("Sacré-Cœur 3", zones, open);
    assert.equal(outcome.kind, "exact");
  });

  it("« Sacré » : propose Sacré-Cœur", () => {
    assert.deepEqual(slugs(searchZones("Sacré", zones, open)), ["sacre-coeur"]);
  });

  it("« Grand » : plusieurs préfixes, en liens", () => {
    assert.deepEqual(slugs(searchZones("Grand", zones, open)).sort(), ["grand-dakar", "grand-yoff"]);
  });

  it("« Gorée » : aucune page, jamais un cul-de-sac (issue « none »)", () => {
    assert.deepEqual(searchZones("Gorée", zones, open), { kind: "none" });
  });

  it("zone connue mais métier non ouvert : issue « closed »", () => {
    const outcome = searchZones("Rufisque", zones, open);
    assert.equal(outcome.kind, "closed");
    if (outcome.kind === "closed") assert.equal(outcome.zone.slug, "rufisque");
  });

  it("sans métier (open = null), toutes les zones sont ouvertes", () => {
    assert.equal(searchZones("Rufisque", zones, null).kind, "exact");
  });

  it("vide ou deux lettres : rien (un préfixe court ne propose rien)", () => {
    assert.deepEqual(searchZones("", zones, open), { kind: "none" });
    assert.deepEqual(searchZones("   ", zones, open), { kind: "none" });
    assert.deepEqual(searchZones("Sa", zones, open), { kind: "none" });
  });
});

describe("cleanQuery", () => {
  it("borne à 40 caractères, première valeur seulement, jamais d'erreur", () => {
    assert.equal(cleanQuery("x".repeat(100)).length, 40);
    assert.equal(cleanQuery(["Yoff", "autre"]), "Yoff");
    assert.equal(cleanQuery(undefined), "");
    assert.equal(cleanQuery("  Yoff  "), "Yoff");
  });
});
