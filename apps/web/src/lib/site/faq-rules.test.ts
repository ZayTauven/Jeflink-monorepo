// Chaque réponse de FAQ est rattachée à sa règle (spec 006, web 13).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

import { FAQ_RULES, FULL_FAQ, SHORT_FAQ } from "./faq-rules.ts";

const fr = JSON.parse(
  readFileSync(new URL("../../../messages/fr.json", import.meta.url), "utf8"),
) as { site: { faq: { items: Record<string, { q: string; a: string }> } } };
const items = fr.site.faq.items;

describe("FAQ et règles", () => {
  it("chaque question affichée a une règle citée, non vide, qui renvoie à une spec ou à une question", () => {
    for (const id of [...FULL_FAQ, ...SHORT_FAQ]) {
      const rule = FAQ_RULES[id];
      assert.ok(rule && /spec|Q\d/.test(rule), `${id} : règle manquante`);
    }
  });

  it("chaque clé de fr.json a sa règle, et chaque règle sa clé : rien d'orphelin", () => {
    assert.deepEqual(Object.keys(items).sort(), Object.keys(FAQ_RULES).sort());
  });

  it("la FAQ complète les affiche toutes, la courte est incluse dedans", () => {
    assert.deepEqual([...FULL_FAQ].sort(), Object.keys(FAQ_RULES).sort());
    for (const id of SHORT_FAQ) assert.ok(FULL_FAQ.includes(id), id);
  });

  it("question et réponse existent ; les réponses à délai ont leur variante sans chiffre", () => {
    for (const [id, item] of Object.entries(items)) {
      assert.ok(item.q && item.a, id);
    }
    for (const id of ["when", "urgent", "problem"]) {
      assert.ok((items[id] as Record<string, string>)?.aNoRules, `${id}.aNoRules`);
    }
  });

  it("aucune réponse ne dit quand payer (Q14) ni ne promet un délai ou un remboursement", () => {
    for (const [id, item] of Object.entries(items)) {
      assert.doesNotMatch(item.a, /à la fin|avant de commencer|rembours|acompte|en 30/i, id);
    }
  });
});
