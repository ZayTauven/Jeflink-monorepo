// Tests des modules purs de /connexion (spec 001, web 2).
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  CHALLENGE_KEY,
  type StoredChallenge,
  clearChallenge,
  loadChallenge,
  saveChallenge,
} from "./challenge-store.ts";
import { webDeviceLabel } from "./device-label.ts";
import { describeLoginError } from "./errors.ts";
import { formatPhoneInput, isPlausiblePhone, phoneForApi } from "./phone.ts";
import { whatsappUrl } from "./support.ts";

describe("phone", () => {
  it("met en forme un numéro national en 2-3-2-2", () => {
    assert.equal(formatPhoneInput("771234567"), "77 123 45 67");
    assert.equal(formatPhoneInput("77 12"), "77 12");
    assert.equal(formatPhoneInput("77-123.45"), "77 123 45");
    assert.equal(formatPhoneInput(""), "");
  });

  it("laisse un numéro international en chiffres", () => {
    assert.equal(formatPhoneInput("+221 77 123 45 67"), "+221771234567");
    assert.equal(formatPhoneInput("00221771234567"), "00221771234567");
  });

  for (const [input, expected] of [
    ["77 123 45 67", "+221771234567"],
    ["771234567", "+221771234567"],
    ["+221 77 123 45 67", "+221771234567"],
    ["00221771234567", "+221771234567"],
    ["221 77 123 45 67", "+221771234567"],
    ["+33 6 12 34 56 78", "+33612345678"],
  ] as const) {
    it(`« ${input} » part en ${expected}`, () => {
      assert.equal(phoneForApi(input, "+221"), expected);
    });
  }

  it("n'envoie qu'un numéro d'au moins 9 chiffres", () => {
    assert.equal(isPlausiblePhone("77 123 45"), false);
    assert.equal(isPlausiblePhone("77 123 45 67"), true);
    assert.equal(isPlausiblePhone("1".repeat(16)), false);
  });
});

function memoryStorage() {
  const values = new Map<string, string>();
  return {
    values,
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => void values.set(key, value),
    removeItem: (key: string) => void values.delete(key),
  };
}

const challenge: StoredChallenge = {
  challenge_id: "6c1f1b8e-0000-4000-8000-000000000000",
  challenge_secret: "secret",
  phone_display: "77 123 45 67",
  code_length: 6,
  expires_at: "2026-10-01T12:30:00Z",
  resend_available_at: "2026-10-01T12:01:00Z",
  deliveries_remaining: 2,
};
const before = Date.parse("2026-10-01T12:10:00Z");
const after = Date.parse("2026-10-01T12:31:00Z");

describe("challenge-store", () => {
  it("garde et rend un challenge vivant", () => {
    const storage = memoryStorage();
    saveChallenge(storage, challenge);
    assert.deepEqual(loadChallenge(storage, before), challenge);
  });

  it("efface un challenge expiré", () => {
    const storage = memoryStorage();
    saveChallenge(storage, challenge);
    assert.equal(loadChallenge(storage, after), null);
    assert.equal(storage.values.has(CHALLENGE_KEY), false);
  });

  it("efface un contenu illisible ou incomplet", () => {
    const storage = memoryStorage();
    storage.setItem(CHALLENGE_KEY, "{pas du json");
    assert.equal(loadChallenge(storage, before), null);
    storage.setItem(CHALLENGE_KEY, JSON.stringify({ ...challenge, challenge_secret: "" }));
    assert.equal(loadChallenge(storage, before), null);
    assert.equal(storage.values.has(CHALLENGE_KEY), false);
  });

  it("stockage bloqué ou absent : aucune exception", () => {
    const throwing = {
      getItem: () => {
        throw new Error("bloqué");
      },
      setItem: () => {
        throw new Error("bloqué");
      },
      removeItem: () => {
        throw new Error("bloqué");
      },
    };
    saveChallenge(throwing, challenge);
    assert.equal(loadChallenge(throwing, before), null);
    clearChallenge(undefined);
  });
});

class ApiError extends Error {
  readonly status: number;
  readonly code: string | undefined;
  readonly body: unknown;
  constructor(status: number, body: { code?: string } & Record<string, unknown>) {
    super(body.code ?? `HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.body = body;
  }
}

describe("describeLoginError", () => {
  it("coupure réseau : « network », jamais un code faux", () => {
    const error = describeLoginError(new TypeError("Failed to fetch"));
    assert.equal(error.key, "network");
    assert.equal(error.restart, false);
  });

  it("code faux : essais restants", () => {
    const error = describeLoginError(
      new ApiError(400, { code: "otp_invalid", attempts_remaining: 3 }),
    );
    assert.deepEqual([error.key, error.values], ["otp_invalid_remaining", { remaining: 3 }]);
    assert.equal(error.support, false);
  });

  it("limite : attente en minutes arrondies au-dessus, avec support", () => {
    const error = describeLoginError(
      new ApiError(429, { code: "otp_rate_limited", retry_after: 61 }),
    );
    assert.deepEqual(error.values, { minutes: 2, seconds: 61 });
    assert.equal(error.key, "otp_rate_limited_wait");
    assert.equal(error.support, true);
  });

  it("région non couverte : écran dédié", () => {
    assert.equal(
      describeLoginError(new ApiError(400, { code: "phone_region_not_supported" })).region,
      true,
    );
  });

  for (const code of ["otp_challenge_invalid", "otp_locked", "otp_resend_exhausted"]) {
    it(`${code} : retour à l'étape téléphone`, () => {
      assert.equal(describeLoginError(new ApiError(400, { code })).restart, true);
    });
  }

  it("validation de format : numéro invalide", () => {
    assert.equal(describeLoginError(new ApiError(400, { code: "invalid" })).key, "phone_invalid");
  });

  it("code inconnu ou panne : message générique avec support", () => {
    const error = describeLoginError(new ApiError(502, { code: "bff_upstream_unavailable" }));
    assert.deepEqual([error.key, error.support], ["generic", true]);
  });
});

describe("whatsappUrl", () => {
  it("lien wa.me avec message encodé", () => {
    assert.equal(
      whatsappUrl("+221 33 000 00 00", "Bonjour & merci"),
      "https://wa.me/221330000000?text=Bonjour%20%26%20merci",
    );
  });

  it("sans numéro configuré : null", () => {
    assert.equal(whatsappUrl(null, "x"), null);
    assert.equal(whatsappUrl("", "x"), null);
  });
});

describe("webDeviceLabel", () => {
  it("navigateur et système", () => {
    assert.equal(
      webDeviceLabel(
        "Mozilla/5.0 (Linux; Android 14; SM-A055F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36",
      ),
      "Chrome · Android",
    );
    assert.equal(
      webDeviceLabel(
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
      ),
      "Safari · iOS",
    );
    assert.equal(webDeviceLabel(""), "Navigateur");
  });
});
