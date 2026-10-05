// Tests des chemins du site public : lien de demande pré-rempli (spec 006).
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { demandPath, tradePath, tradeZonePath } from "./paths.ts";

describe("demandPath", () => {
  it("métier et quartier, dans l'ordre de la spec", () => {
    assert.equal(
      demandPath({ metier: "plombier", quartier: "ouakam" }),
      "/demande?metier=plombier&quartier=ouakam",
    );
  });

  it("service, puis urgence", () => {
    assert.equal(
      demandPath({ metier: "plombier", quartier: "ouakam", service: "fuite", urgence: true }),
      "/demande?metier=plombier&quartier=ouakam&service=fuite&urgence=1",
    );
  });

  it("le service est ignoré sans métier ; rien à pré-remplir : l'URL nue", () => {
    assert.equal(demandPath({ service: "fuite" }), "/demande");
    assert.equal(demandPath(), "/demande");
    assert.equal(demandPath({ metier: null, quartier: undefined, urgence: false }), "/demande");
  });

  it("une valeur étrange est encodée, jamais recopiée telle quelle", () => {
    assert.equal(demandPath({ metier: "a&b=c" }), "/demande?metier=a%26b%3Dc");
  });
});

describe("chemins de pages", () => {
  it("métier et métier × quartier : slugs encodés", () => {
    assert.equal(tradePath("plombier"), "/plombier");
    assert.equal(tradeZonePath("plombier", "sacre-coeur"), "/plombier/sacre-coeur");
    assert.equal(tradeZonePath("a/b", "c d"), "/a%2Fb/c%20d");
  });
});
