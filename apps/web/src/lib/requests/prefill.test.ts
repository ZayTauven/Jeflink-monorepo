// Tests du pré-remplissage de /demande par l'URL (spec 006, web 9).
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { safeNextPath } from "@jeflink/api-client/paths";

import { demandPath } from "../site/paths.ts";
import { emptyDraft } from "./draft.ts";
import { applyPrefill, readPrefill } from "./prefill.ts";
import type { TradeOption, ZoneOption } from "./search.ts";

const trades: TradeOption[] = [
  {
    slug: "plombier",
    name: "Plomberie",
    aliases: [],
    services: [
      { slug: "fuite", name: "Fuite", aliases: [], urgent: true },
      { slug: "robinet", name: "Robinet", aliases: [], urgent: false },
    ],
  },
  {
    slug: "electricien",
    name: "Électricité",
    aliases: [],
    services: [{ slug: "panne", name: "Panne", aliases: [], urgent: true }],
  },
];
const zones: ZoneOption[] = [
  { slug: "ouakam", name: "Ouakam", city: "dakar", aliases: [] },
  { slug: "sacre-coeur", name: "Sacré-Cœur", city: "dakar", aliases: [] },
];

describe("readPrefill", () => {
  it("métier, quartier, service et urgence connus du catalogue", () => {
    assert.deepEqual(
      readPrefill(
        { metier: "plombier", quartier: "ouakam", service: "fuite", urgence: "1" },
        trades,
        zones,
      ),
      { tradeSlug: "plombier", serviceSlug: "fuite", zoneSlug: "ouakam", urgent: true },
    );
  });

  it("inconnu : ignoré sans bruit, le reste est gardé", () => {
    assert.deepEqual(readPrefill({ metier: "inconnu", quartier: "ouakam" }, trades, zones), {
      zoneSlug: "ouakam",
    });
    assert.deepEqual(readPrefill({ metier: "plombier", quartier: "gorée" }, trades, zones), {
      tradeSlug: "plombier",
    });
  });

  it("un service d'un autre métier, ou sans métier, est ignoré", () => {
    assert.deepEqual(readPrefill({ metier: "plombier", service: "panne" }, trades, zones), {
      tradeSlug: "plombier",
    });
    assert.deepEqual(readPrefill({ service: "fuite" }, trades, zones), {});
  });

  it("urgence : seulement « 1 »", () => {
    for (const value of ["0", "true", "oui", "", undefined]) {
      assert.deepEqual(readPrefill({ urgence: value }, trades, zones), {}, String(value));
    }
  });

  it("valeurs piégées : trop longues, majuscules, scripts, répétées", () => {
    for (const value of [
      "Plombier",
      "plombier ",
      "<script>",
      "../x",
      "a".repeat(51),
      "plombier'--",
      "__proto__",
    ]) {
      assert.deepEqual(readPrefill({ metier: value }, trades, zones), {}, value);
    }
    assert.deepEqual(readPrefill({ metier: ["plombier", "electricien"] }, trades, zones), {
      tradeSlug: "plombier",
    });
  });

  it("rien dans l'URL : rien à pré-remplir", () => {
    assert.deepEqual(readPrefill({}, trades, zones), {});
  });
});

describe("applyPrefill", () => {
  const draft = {
    ...emptyDraft(),
    tradeSlug: "plombier",
    serviceSlug: "robinet",
    zoneSlug: "sacre-coeur",
    description: "Ça coule sous l'évier",
    landmark: "Près du marché",
    urgent: false,
  };

  it("sans valeur d'URL : le brouillon reste tel quel", () => {
    assert.equal(applyPrefill(draft, {}), draft);
  });

  it("l'URL gagne sur le métier, le quartier et l'urgence ; le reste du brouillon est gardé", () => {
    const next = applyPrefill(draft, { zoneSlug: "ouakam", urgent: true });
    assert.equal(next.zoneSlug, "ouakam");
    assert.equal(next.urgent, true);
    assert.equal(next.tradeSlug, "plombier");
    assert.equal(next.serviceSlug, "robinet", "même métier : le service reste");
    assert.equal(next.description, draft.description);
    assert.equal(next.landmark, draft.landmark);
  });

  it("le service est vidé si le métier change", () => {
    const next = applyPrefill(draft, { tradeSlug: "electricien" });
    assert.equal(next.tradeSlug, "electricien");
    assert.equal(next.serviceSlug, "");
  });

  it("le service de l'URL remplace celui du brouillon, même métier ou non", () => {
    assert.equal(
      applyPrefill(draft, { tradeSlug: "plombier", serviceSlug: "fuite" }).serviceSlug,
      "fuite",
    );
    assert.equal(
      applyPrefill(draft, { tradeSlug: "electricien", serviceSlug: "panne" }).serviceSlug,
      "panne",
    );
  });

  it("un quartier de l'URL remplace « autre quartier »", () => {
    const other = { ...draft, zoneSlug: "", otherZone: true, zoneText: "Gorée" };
    const next = applyPrefill(other, { zoneSlug: "ouakam" });
    assert.equal(next.otherZone, false);
    assert.equal(next.zoneText, "");
    assert.equal(next.zoneSlug, "ouakam");
  });

  it("l'urgence absente de l'URL ne décoche pas celle du brouillon", () => {
    assert.equal(applyPrefill({ ...draft, urgent: true }, { zoneSlug: "ouakam" }).urgent, true);
  });

  it("brouillon vide : le formulaire part de l'URL", () => {
    const next = applyPrefill(emptyDraft(), {
      tradeSlug: "plombier",
      zoneSlug: "ouakam",
      urgent: true,
    });
    assert.equal(next.tradeSlug, "plombier");
    assert.equal(next.zoneSlug, "ouakam");
    assert.equal(next.urgent, true);
  });
});

describe("retour après connexion", () => {
  it("le lien du site traverse safeNextPath avec sa requête intacte", () => {
    const link = demandPath({
      metier: "plombier",
      quartier: "ouakam",
      service: "fuite",
      urgence: true,
    });
    assert.equal(safeNextPath(link), link);
    const login = `/connexion?next=${encodeURIComponent(link)}`;
    assert.equal(safeNextPath(new URL(login, "https://x.invalid").searchParams.get("next")), link);
  });
});
