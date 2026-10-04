// Tests des erreurs des actions sur une réservation (spec 004, web 4).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

import { DISPUTE_REASONS } from "./dispute.ts";
import { BOOKING_ERROR_CODES, bookingError, describeBookingError, isStale } from "./errors.ts";
import { NEGATIVE_TAGS, POSITIVE_TAGS } from "./review.ts";
import { STEP_KEYS } from "./steps.ts";

class ApiError extends Error {
  readonly status: number;
  readonly code: string | undefined;
  constructor(status: number, code?: string) {
    super(code ?? `HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

const fr = JSON.parse(
  readFileSync(new URL("../../../messages/fr.json", import.meta.url), "utf8"),
) as { bookings: Record<string, Record<string, unknown>> };

/** Codes du contrat de l'API (spec 004 et corrections de la revue sécurité), tous statuts. */
const API_CODES = [
  "transition_not_allowed",
  "no_show_too_early",
  "no_show_contest_closed",
  "completion_code_locked",
  "completion_code_regen_limit",
  "photo_limit_reached",
  "idempotency_key_reused",
  "amendment_pending",
  "amendment_limit",
  "amendment_not_pending",
  "dispute_window_closed",
  "review_window_closed",
  "review_not_allowed",
  "provider_not_verified",
  "too_early",
  "amendment_total_mismatch",
  "before_photos_required",
  "after_photos_required",
  "completion_code_invalid",
  "completion_proof_required",
  "no_code_reason_invalid",
  "occurred_at_invalid",
  "photo_invalid",
  "amendment_total_invalid",
  "amendment_confirmation_required",
  "amendment_reason_invalid",
  "note_invalid",
  "reason_invalid",
  "description_invalid",
  "review_invalid",
  "text_too_long",
  "invalid",
  "idempotency_key_required",
  "photo_too_large",
  "sms_limit_reached",
];

describe("erreurs de réservation", () => {
  it("chaque code de l'API est connu et a son libellé fr", () => {
    const errors = fr.bookings.errors as Record<string, string>;
    for (const code of API_CODES) {
      assert.ok(BOOKING_ERROR_CODES.includes(code), `code inconnu : ${code}`);
    }
    const missing = BOOKING_ERROR_CODES.filter((code) => !errors[code]);
    assert.deepEqual(missing, []);
  });
  it("décrit une ApiError par son code", () => {
    assert.equal(
      describeBookingError(new ApiError(409, "dispute_window_closed")).key,
      "dispute_window_closed",
    );
    assert.equal(
      describeBookingError(new ApiError(429, "sms_limit_reached")).code,
      "sms_limit_reached",
    );
  });
  it("sans code lisible : un libellé proche du statut, jamais un message brut", () => {
    assert.equal(describeBookingError(new ApiError(401)).login, true);
    assert.equal(describeBookingError(new ApiError(404)).code, "not_found");
    assert.equal(describeBookingError(new ApiError(413)).code, "photo_too_large");
    assert.equal(describeBookingError(new ApiError(500, "inconnu")).code, "generic");
  });
  it("une coupure du navigateur est « network », une panne serveur « generic »", () => {
    assert.equal(describeBookingError(new TypeError("fetch failed")).code, "network");
    assert.equal(describeBookingError(new Error("x"), "generic").code, "generic");
  });
  it("les impasses proposent le support, les pages périmées « Actualiser »", () => {
    assert.equal(bookingError("completion_code_regen_limit").support, true);
    assert.equal(bookingError("review_invalid").support, false);
    assert.equal(isStale("amendment_not_pending"), true);
    assert.equal(isStale("photo_invalid"), false);
  });
  it("les listes fermées (étapes, motifs, puces) ont leurs libellés", () => {
    const missing = (group: string, sub: string, keys: readonly string[]) => {
      const node = fr.bookings[group]?.[sub] as Record<string, string> | undefined;
      return keys.filter((key) => !node?.[key]);
    };
    assert.deepEqual(missing("progress", "steps", STEP_KEYS), []);
    assert.deepEqual(missing("progress", "hint", [...STEP_KEYS.slice(0, 5), "disputed"]), []);
    assert.deepEqual(missing("dispute", "reasons", DISPUTE_REASONS), []);
    assert.deepEqual(missing("review", "tags", [...POSITIVE_TAGS, ...NEGATIVE_TAGS]), []);
    assert.deepEqual(missing("review", "ratings", ["1", "2", "3", "4", "5"]), []);
    assert.deepEqual(
      missing("amendment", "reason", ["visit_diagnosis", "extra_work", "parts", "other"]),
      [],
    );
    assert.deepEqual(missing("dispute", "decisions", ["for_client", "for_pro", "no_fault"]), []);
  });
});
