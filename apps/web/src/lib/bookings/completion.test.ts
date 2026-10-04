// Tests de la fin de mission : contestation, avis, note (spec 004, web 3).
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { formatDeadline } from "../requests/format.ts";
import { disputeWindowOpen, validateDispute } from "./dispute.ts";
import { formatAverage, sanitizeTags, tagsFor, validateReview } from "./review.ts";

describe("fenêtre de contestation (heure de Dakar)", () => {
  const deadline = "2026-10-05T14:30:00Z";
  it("ouverte avant l'échéance, fermée à l'échéance et après", () => {
    assert.equal(disputeWindowOpen(deadline, "2026-10-05T14:29:59Z"), true);
    assert.equal(disputeWindowOpen(deadline, "2026-10-05T14:30:00Z"), false);
    assert.equal(disputeWindowOpen(null, "2026-10-05T10:00:00Z"), false);
    assert.equal(disputeWindowOpen("x", "2026-10-05T10:00:00Z"), false);
  });
  it("l'échéance s'écrit en heure de Dakar : l'heure seule le jour même, la date sinon", () => {
    assert.equal(formatDeadline(deadline, "2026-10-05T09:00:00Z"), "14 h 30");
    assert.equal(formatDeadline(deadline, "2026-10-03T09:00:00Z"), "5 oct. · 14 h 30");
  });
  it("motif de la liste et texte de 10 à 1 000 caractères", () => {
    assert.equal(validateDispute("", "Le robinet fuit toujours"), "reason");
    assert.equal(validateDispute("nimporte", "Le robinet fuit toujours"), "reason");
    assert.equal(validateDispute("poor_quality", "trop court"), null);
    assert.equal(validateDispute("poor_quality", "court"), "description");
    assert.equal(validateDispute("poor_quality", "   court   "), "description");
    assert.equal(validateDispute("other", "x".repeat(1001)), "description");
    assert.equal(validateDispute("other", "x".repeat(1000)), null);
  });
});

describe("avis", () => {
  it("une note suffit", () => {
    const check = validateReview({ rating: 5 });
    assert.deepEqual(check.ok && check.value, { rating: 5, tags: [], comment: "" });
  });
  it("refuse une note absente, hors 1 à 5 ou non entière", () => {
    for (const rating of [0, 6, 3.5, "4", null, undefined]) {
      assert.deepEqual(validateReview({ rating }), { ok: false, problem: "rating" });
    }
  });
  it("les puces négatives ne sont permises que sous 3 étoiles", () => {
    assert.ok(tagsFor(2).includes("late"));
    assert.ok(!tagsFor(3).includes("late"));
    assert.ok(tagsFor(5).includes("on_time"));
    assert.deepEqual(sanitizeTags(4, ["on_time", "late"]), ["on_time"]);
    assert.deepEqual(validateReview({ rating: 4, tags: ["late"] }), { ok: false, problem: "tags" });
    assert.equal(validateReview({ rating: 1, tags: ["late", "messy"] }).ok, true);
  });
  it("refuse une puce inconnue ou mal typée", () => {
    assert.equal(validateReview({ rating: 5, tags: ["inconnue"] }).ok, false);
    assert.equal(validateReview({ rating: 5, tags: [3] }).ok, false);
  });
  it("commentaire facultatif, 500 caractères au plus", () => {
    assert.equal(validateReview({ rating: 5, comment: "x".repeat(500) }).ok, true);
    assert.deepEqual(validateReview({ rating: 5, comment: "x".repeat(501) }), {
      ok: false,
      problem: "comment",
    });
  });
  it("moyenne avec une décimale et une virgule", () => {
    assert.equal(formatAverage(4.8), "4,8");
    assert.equal(formatAverage(5), "5,0");
    assert.equal(formatAverage(4.349), "4,3");
  });
});
