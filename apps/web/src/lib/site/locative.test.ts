// Tests du locatif des quartiers (spec 006) : la grammaire est une donnée, le repli une clé i18n.
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { tradeZoneTitle, zoneLocative } from "./locative.ts";

const fallback = (name: string) => `à ${name}`;

describe("zoneLocative", () => {
  it("le locatif saisi par l'Ops, tel quel", () => {
    assert.equal(
      zoneLocative({ name: "Almadies", locative: { fr: "aux Almadies", wo: null } }, fallback),
      "aux Almadies",
    );
    assert.equal(
      zoneLocative({ name: "Plateau", locative: { fr: "au Plateau", wo: null } }, fallback),
      "au Plateau",
    );
  });

  it("repli « à {nom} » sans locatif saisi, ou saisi vide", () => {
    assert.equal(zoneLocative({ name: "Ouakam" }, fallback), "à Ouakam");
    assert.equal(zoneLocative({ name: "Ouakam", locative: null }, fallback), "à Ouakam");
    assert.equal(
      zoneLocative({ name: " Ouakam ", locative: { fr: "  ", wo: null } }, fallback),
      "à Ouakam",
    );
  });

  it("wolof : le texte wo s'il existe, sinon le français", () => {
    const zone = { name: "Ouakam", locative: { fr: "à Ouakam", wo: "ci Ouakam" } };
    assert.equal(zoneLocative(zone, fallback, "wo"), "ci Ouakam");
    assert.equal(
      zoneLocative({ name: "Ouakam", locative: { fr: "à Ouakam", wo: null } }, fallback, "wo"),
      "à Ouakam",
    );
  });
});

describe("tradeZoneTitle", () => {
  it("{seo_title} {locatif}", () => {
    assert.equal(tradeZoneTitle("Plombier", "à Ouakam"), "Plombier à Ouakam");
    assert.equal(
      tradeZoneTitle("Femme de ménage et nettoyage", "aux Almadies"),
      "Femme de ménage et nettoyage aux Almadies",
    );
  });
});
