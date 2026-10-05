// Tests de la configuration du site public (spec 006, web 1) : SITE_URL, SITE_INDEXABLE,
// SITE_LEGAL_NAME, SUPPORT_PHONE_NUMBER, et le refus de démarrer d'une indexation incomplète.
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { FALLBACK_SITE_ORIGIN, readSiteConfig } from "./site-config.ts";

const dev = { NODE_ENV: "development" };
const complete = {
  NODE_ENV: "production",
  SUPPORT_WHATSAPP_NUMBER: "+221 33 000 00 00",
  SUPPORT_PHONE_NUMBER: "+221 33 000 00 01",
  SITE_URL: "https://jeflink.sn",
  SITE_LEGAL_NAME: "Jeflink SARL",
  SITE_INDEXABLE: "true",
};

describe("readSiteConfig : site public", () => {
  it("dev sans rien : non indexable, aucune valeur", () => {
    assert.deepEqual(readSiteConfig(dev), {
      supportWhatsapp: null,
      supportPhone: null,
      siteUrl: null,
      indexable: false,
      legalName: null,
    });
  });

  it("configuration complète : numéro d'appel avec « + », origine sans barre, raison sociale", () => {
    const config = readSiteConfig(complete);
    assert.equal(config.indexable, true);
    assert.equal(config.supportPhone, "+221330000001");
    assert.equal(config.supportWhatsapp, "221330000000");
    assert.equal(config.siteUrl, "https://jeflink.sn");
    assert.equal(config.legalName, "Jeflink SARL");
    assert.equal(
      readSiteConfig({ ...complete, SITE_URL: "https://jeflink.sn/" }).siteUrl,
      "https://jeflink.sn",
    );
  });

  it("SITE_INDEXABLE : faux par défaut, true ou false seulement", () => {
    assert.equal(readSiteConfig({ ...complete, SITE_INDEXABLE: undefined }).indexable, false);
    assert.equal(readSiteConfig({ ...complete, SITE_INDEXABLE: "false" }).indexable, false);
    assert.equal(readSiteConfig({ ...complete, SITE_INDEXABLE: " TRUE " }).indexable, true);
    for (const typo of ["1", "yes", "ture", "oui"]) {
      assert.throws(() => readSiteConfig({ ...complete, SITE_INDEXABLE: typo }), /SITE_INDEXABLE/);
    }
  });

  for (const name of [
    "SITE_URL",
    "SUPPORT_WHATSAPP_NUMBER",
    "SUPPORT_PHONE_NUMBER",
    "SITE_LEGAL_NAME",
  ]) {
    it(`SITE_INDEXABLE=true sans ${name} : refus de démarrer, nom de variable seulement`, () => {
      assert.throws(
        () => readSiteConfig({ ...complete, [name]: " " }),
        (error: Error) => {
          assert.ok(error.message.includes(name));
          for (const secret of ["jeflink.sn", "Jeflink SARL", "330000"]) {
            assert.ok(!error.message.includes(secret), "aucune valeur dans le message");
          }
          return true;
        },
      );
    });
  }

  it("SITE_INDEXABLE=true exige https", () => {
    assert.throws(() => readSiteConfig({ ...complete, SITE_URL: "http://jeflink.sn" }), /SITE_URL/);
  });

  it("indexable faux : les variables du site restent facultatives (staging, local)", () => {
    const config = readSiteConfig({ ...dev, SITE_URL: "http://localhost:3000" });
    assert.equal(config.siteUrl, "http://localhost:3000");
    assert.equal(config.indexable, false);
    assert.equal(new URL(FALLBACK_SITE_ORIGIN).origin, FALLBACK_SITE_ORIGIN);
  });

  it("formats refusés : URL à chemin, protocole étranger, numéro non E.164", () => {
    assert.throws(() => readSiteConfig({ ...dev, SITE_URL: "https://jeflink.sn/fr" }), /SITE_URL/);
    assert.throws(() => readSiteConfig({ ...dev, SITE_URL: "ftp://jeflink.sn" }), /SITE_URL/);
    assert.throws(() => readSiteConfig({ ...dev, SITE_URL: "pas une url" }), /SITE_URL/);
    assert.throws(
      () => readSiteConfig({ ...dev, SUPPORT_PHONE_NUMBER: "tel:33" }),
      /SUPPORT_PHONE_NUMBER/,
    );
  });
});
