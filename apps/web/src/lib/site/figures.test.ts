// Tests du choix des gros chiffres (spec 006, Q5) : vrais par construction, preuves au-delà des
// seuils seulement, rien sous seuil.
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { chooseFigures, type PublicStats } from "./figures.ts";

const rules = { max_quotes_per_request: 3, dispute_window_hours: 48 };
const base: PublicStats = { missions_completed: null, rating: null, verified_pros: null, rules };

const kinds = (stats: PublicStats | null) => chooseFigures(stats).map((figure) => figure.kind);

describe("chooseFigures", () => {
  it("sous tous les seuils : règles et « 0 F », valeurs lues dans `rules`", () => {
    assert.deepEqual(chooseFigures(base), [
      { kind: "quotes", value: 3 },
      { kind: "dispute", hours: 48 },
      { kind: "fees" },
    ]);
  });

  it("les valeurs suivent `rules` : rien n'est recopié", () => {
    const figures = chooseFigures({
      ...base,
      rules: { max_quotes_per_request: 5, dispute_window_hours: 72 },
    });
    assert.deepEqual(figures[0], { kind: "quotes", value: 5 });
    assert.deepEqual(figures[1], { kind: "dispute", hours: 72 });
  });

  it("une preuve réelle remplace le délai ; « 0 F » reste", () => {
    assert.deepEqual(kinds({ ...base, missions_completed: 120 }), ["quotes", "missions", "fees"]);
  });

  it("deux preuves remplacent le délai, puis le nombre de devis ; « 0 F » reste toujours", () => {
    assert.deepEqual(
      kinds({ ...base, missions_completed: 120, rating: { average: 4.6, count: 31 } }),
      ["rating", "missions", "fees"],
    );
    assert.deepEqual(
      kinds({
        missions_completed: 120,
        rating: { average: 4.6, count: 31 },
        verified_pros: 20,
        rules,
      }),
      ["rating", "missions", "fees"],
    );
  });

  it("jamais plus de 3 chiffres", () => {
    for (const stats of [base, { ...base, missions_completed: 60, verified_pros: 8 }]) {
      assert.ok(chooseFigures(stats).length <= 3);
    }
  });

  it("zéro, null ou valeur invalide : rien n'est affiché à la place (jamais « 0 »)", () => {
    const figures = chooseFigures({
      missions_completed: 0,
      rating: { average: 0, count: 0 },
      verified_pros: 0,
      rules,
    });
    assert.deepEqual(
      figures.map((figure) => figure.kind),
      ["quotes", "dispute", "fees"],
    );
    assert.ok(!kinds({ ...base, missions_completed: Number.NaN }).includes("missions"));
  });

  it("API sans réponse : seul « 0 F » (aucune règle à citer, aucune preuve)", () => {
    assert.deepEqual(chooseFigures(null), [{ kind: "fees" }]);
    assert.deepEqual(chooseFigures(undefined), [{ kind: "fees" }]);
  });

  it("règles absentes mais preuves disponibles : elles complètent, « 0 F » en dernier", () => {
    assert.deepEqual(kinds({ ...base, rules: null, missions_completed: 50, verified_pros: 5 }), [
      "pros",
      "missions",
      "fees",
    ]);
  });
});
