// Contrôles automatiques de la copie publique `site.*` (spec 006, « Contenu et i18n ») : phrases
// de 12 mots au plus, aucune formule fausse en V1, aucun nom de moyen de paiement.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

import type { Messages } from "./client-messages.ts";

const fr = JSON.parse(
  readFileSync(new URL("../../messages/fr.json", import.meta.url), "utf8"),
) as Messages;

function strings(node: string | Messages | undefined, prefix: string): [string, string][] {
  if (node === undefined) return [];
  if (typeof node === "string") return [[prefix, node]];
  return Object.entries(node).flatMap(([key, value]) => strings(value, `${prefix}.${key}`));
}

const site = strings(fr.site, "site");

const FORBIDDEN = [
  /devis gratuit/i,
  /rembours/i,
  /paiement s[ée]curis/i,
  /payez [àa] la fin/i,
  /30 ?min/i,
  /24 ?h ?\/ ?24/i,
  /\b(wave|orange money|free money|wizall|visa|mastercard|paypal)\b/i,
];

describe("copie site.*", () => {
  it("existe", () => {
    assert.ok(site.length > 20);
  });

  it("phrases de 12 mots au plus", () => {
    for (const [key, text] of site) {
      // Les variables et les formules ICU (select) comptent pour un mot.
      const plain = text.replace(/\{[^{}]*\}/g, "x").replace(/[{}]/g, " ");
      for (const sentence of plain.split(/(?<=[.!?…])\s+/)) {
        const words = sentence.split(/\s+/).filter((word) => /[\p{L}\d]/u.test(word));
        assert.ok(words.length <= 12, `${key} : ${words.length} mots (« ${sentence} »)`);
      }
    }
  });

  it("aucune formule fausse en V1, aucun moyen de paiement nommé", () => {
    for (const [key, text] of site) {
      for (const pattern of FORBIDDEN) assert.doesNotMatch(text, pattern, key);
    }
  });
});
