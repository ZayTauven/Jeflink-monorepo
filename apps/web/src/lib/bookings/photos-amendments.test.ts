// Tests des photos et des avenants (spec 004, web 2).
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { changePercent, direction, needsConfirmation, pendingAmendment } from "./amendments.ts";
import { isExpired, photosOf } from "./photos.ts";

const base = { status: "proposed", previous_amount_xof: 20000, total_xof: 35000 } as const;

describe("avenants", () => {
  it("hausse au-delà du seuil : confirmation en plus du geste", () => {
    const a = { ...base, change_pct: 75, requires_confirmation: true };
    assert.equal(direction(a), "up");
    assert.equal(needsConfirmation(a), true);
    assert.equal(changePercent(a), 75);
  });
  it("hausse sous le seuil : pas de confirmation", () => {
    assert.equal(
      needsConfirmation({
        ...base,
        total_xof: 22000,
        change_pct: 10,
        requires_confirmation: false,
      }),
      false,
    );
  });
  it("une baisse n'en demande jamais, même si l'API la marquait", () => {
    const down = { ...base, total_xof: 8000, change_pct: -60, requires_confirmation: true };
    assert.equal(direction(down), "down");
    assert.equal(needsConfirmation(down), false);
    assert.equal(changePercent(down), 60);
  });
  it("un avenant déjà décidé n'a plus de confirmation", () => {
    assert.equal(
      needsConfirmation({
        ...base,
        status: "accepted",
        change_pct: 75,
        requires_confirmation: true,
      }),
      false,
    );
  });
  it("l'écart est recalculé si l'API ne le donne pas", () => {
    assert.equal(changePercent({ ...base, change_pct: Number.NaN }), 75);
  });
  it("trouve l'avenant en attente", () => {
    assert.equal(
      pendingAmendment([{ status: "declined" }, { status: "proposed" }] as const)?.status,
      "proposed",
    );
    assert.equal(pendingAmendment([{ status: "accepted" }] as const), undefined);
  });
});

describe("photos", () => {
  it("une URL signée expire à son échéance, et dans le doute on recharge", () => {
    const exp = "2026-10-04T10:10:00Z";
    assert.equal(isExpired(exp, "2026-10-04T10:00:00Z"), false);
    assert.equal(isExpired(exp, "2026-10-04T10:10:00Z"), true);
    assert.equal(isExpired("n'importe quoi", "2026-10-04T10:00:00Z"), true);
  });
  it("groupe par phase, dans l'ordre de prise, sans les photos en échec", () => {
    const photos = [
      { phase: "after", status: "ready", created_at: "2026-10-04T12:00:00Z" },
      { phase: "before", status: "ready", created_at: "2026-10-04T09:05:00Z" },
      { phase: "before", status: "failed", created_at: "2026-10-04T09:00:00Z" },
      { phase: "before", status: "ready", created_at: "2026-10-04T09:01:00Z" },
    ] as const;
    assert.deepEqual(
      photosOf(photos, "before").map((p) => p.created_at),
      ["2026-10-04T09:01:00Z", "2026-10-04T09:05:00Z"],
    );
    assert.equal(photosOf(photos, "after").length, 1);
  });
});
