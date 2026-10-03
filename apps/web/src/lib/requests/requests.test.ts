// Tests des modules purs du parcours demande (spec 003, web 1 à 3).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

import {
  DRAFT_KEY,
  DRAFT_MAX_AGE_MS,
  type Draft,
  clearDraft,
  emptyDraft,
  isIdempotencyKey,
  loadDraft,
  newIdempotencyKey,
  parseDraft,
  saveDraft,
  serializeDraft,
} from "./draft.ts";
import { REQUEST_ERROR_CODES, candidatesFrom, describeRequestError } from "./errors.ts";
import { reconcileDraft } from "./catalog.ts";
import { dakarToday, formatClock, formatDateTime, formatXof, slotLabel } from "./format.ts";
import { cursorFromNext, isUuid, safeCursor } from "./ids.ts";
import { buildRequestBody, hasErrors, validateDraft, withZoneChoice } from "./payload.ts";
import { callAction } from "./result.ts";
import { choosableQuotes, readableLabel, sortQuotes } from "./quotes.ts";
import { searchTrades, searchZones } from "./search.ts";
import { providerWithdrew, validateCancel } from "./status.ts";

class ApiError extends Error {
  readonly status: number;
  readonly code: string | undefined;
  readonly body: unknown;
  constructor(status: number, body: unknown) {
    const code =
      typeof body === "object" && body !== null && "code" in body && typeof body.code === "string"
        ? body.code
        : undefined;
    super(code ?? `HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.body = body;
  }
}

describe("formatXof", () => {
  it("sépare les milliers par une espace insécable, sans décimales", () => {
    assert.equal(formatXof(25000), "25 000 F CFA");
    assert.equal(formatXof(950), "950 F CFA");
    assert.equal(formatXof(1250000), "1 250 000 F CFA");
    assert.equal(formatXof(0), "0 F CFA");
  });
  it("n'invente jamais de décimales", () => {
    assert.equal(formatXof(15000.9), "15 000 F CFA");
    assert.equal(formatXof(Number.NaN), "0 F CFA");
  });
  it("n'utilise pas l'espace fine U+202F, absente de Funnel Display", () => {
    assert.ok(!formatXof(1234567).includes(" "));
  });
});

describe("slotLabel", () => {
  // 2026-10-03 est un samedi ; Dakar = UTC, sans heure d'été.
  const now = "2026-10-03T10:00:00Z";
  it("« Demain matin » pour le lendemain, 8 h à 12 h", () => {
    const label = slotLabel("2026-10-04T08:00:00Z", "2026-10-04T12:00:00Z", now);
    assert.deepEqual(label?.day, { kind: "tomorrow" });
    assert.equal(label?.period, "morning");
    assert.equal(label?.from, "8 h");
    assert.equal(label?.to, "12 h");
  });
  it("aujourd'hui, après-midi et soir", () => {
    assert.deepEqual(slotLabel("2026-10-03T12:00:00Z", "2026-10-03T17:00:00Z", now)?.day, {
      kind: "today",
    });
    assert.equal(
      slotLabel("2026-10-03T12:00:00Z", "2026-10-03T17:00:00Z", now)?.period,
      "afternoon",
    );
    assert.equal(slotLabel("2026-10-03T17:00:00Z", "2026-10-03T21:00:00Z", now)?.period, "evening");
  });
  it("un jour de la semaine dans les 6 jours, une date au-delà", () => {
    assert.deepEqual(slotLabel("2026-10-06T08:00:00Z", "2026-10-06T12:00:00Z", now)?.day, {
      kind: "weekday",
      text: "Mardi",
    });
    const far = slotLabel("2026-10-20T08:00:00Z", "2026-10-20T12:00:00Z", now)?.day;
    assert.equal(far?.kind, "date");
  });
  it("compte les jours à Dakar, pas à l'heure de l'appareil", () => {
    // 23 h 30 à Dakar : le lendemain commence dans une demi-heure, pas dans 24 h.
    assert.deepEqual(
      slotLabel("2026-10-04T08:00:00Z", "2026-10-04T12:00:00Z", "2026-10-03T23:30:00Z")?.day,
      { kind: "tomorrow" },
    );
  });
  it("renvoie null pour une date illisible", () => {
    assert.equal(slotLabel("n'importe quoi", "2026-10-04T12:00:00Z", now), null);
  });
});

describe("heures de Dakar", () => {
  it("formatClock", () => {
    assert.equal(formatClock("2026-10-03T14:30:00Z"), "14 h 30");
    assert.equal(formatClock("2026-10-03T08:05:00Z"), "8 h 05");
    assert.equal(formatClock("nope"), "");
  });
  it("formatDateTime : jour court puis heure", () => {
    assert.equal(formatDateTime("2026-10-12T14:30:00Z"), "12 oct. · 14 h 30");
  });
  it("dakarToday", () => {
    assert.equal(dakarToday("2026-10-03T23:59:00Z"), "2026-10-03");
  });
});

describe("sortQuotes", () => {
  const q = (id: string, start: string, end: string, total = 10000) => ({
    public_id: id,
    slot_start: start,
    slot_end: end,
    total_xof: total,
    status: "submitted" as const,
  });
  it("trie par créneau le plus proche, jamais par prix", () => {
    const sorted = sortQuotes([
      q("c", "2026-10-06T08:00:00Z", "2026-10-06T12:00:00Z", 5000),
      q("a", "2026-10-04T08:00:00Z", "2026-10-04T12:00:00Z", 30000),
      q("b", "2026-10-05T08:00:00Z", "2026-10-05T12:00:00Z", 1000),
    ]);
    assert.deepEqual(
      sorted.map((x) => x.public_id),
      ["a", "b", "c"],
    );
  });
  it("à créneau égal, ordre stable par fin puis identifiant (pas par prix)", () => {
    const sorted = sortQuotes([
      q("z", "2026-10-04T08:00:00Z", "2026-10-04T12:00:00Z", 1),
      q("m", "2026-10-04T08:00:00Z", "2026-10-04T11:00:00Z", 99999),
      q("a", "2026-10-04T08:00:00Z", "2026-10-04T12:00:00Z", 50000),
    ]);
    assert.deepEqual(
      sorted.map((x) => x.public_id),
      ["m", "a", "z"],
    );
  });
  it("ne modifie pas l'entrée", () => {
    const input = [q("b", "2026-10-05T08:00:00Z", "x"), q("a", "2026-10-04T08:00:00Z", "x")];
    sortQuotes(input);
    assert.equal(input[0]?.public_id, "b");
  });
  it("choosableQuotes garde les devis en lice", () => {
    const quotes = [
      { status: "submitted" as const },
      { status: "held" as const },
      { status: "declined" as const },
      { status: "accepted" as const },
    ];
    assert.equal(choosableQuotes(quotes).length, 2);
  });
});

describe("libellés masqués", () => {
  it("un libellé de ligne masqué n'est pas affiché", () => {
    assert.equal(readableLabel("••••••••"), "");
    assert.equal(readableLabel(" Main-d'œuvre "), "Main-d'œuvre");
  });
});

describe("brouillon", () => {
  const now = Date.parse("2026-10-03T10:00:00Z");
  const filled: Draft = {
    ...emptyDraft(),
    tradeSlug: "plomberie",
    zoneSlug: "ouakam",
    landmark: "près de la boutique, portail bleu",
    description: "Fuite sous l'évier",
    idempotencyKey: newIdempotencyKey(() => "123e4567-e89b-12d3-a456-426614174000"),
  };

  function memory() {
    const data = new Map<string, string>();
    return {
      data,
      getItem: (k: string) => data.get(k) ?? null,
      setItem: (k: string, v: string) => void data.set(k, v),
      removeItem: (k: string) => void data.delete(k),
    };
  }

  it("fait l'aller-retour", () => {
    const back = parseDraft(serializeDraft(filled, now), now);
    assert.deepEqual(back, filled);
  });
  it("ne contient jamais la position", () => {
    const withPosition = { ...filled, location: { lat: 14.7, lon: -17.5 }, lat: 14.7 };
    const stored = serializeDraft(withPosition as Draft, now);
    // La position n'est pas un champ du brouillon : si un appelant la glisse, elle ne revient pas.
    const back = parseDraft(stored, now) as Record<string, unknown>;
    assert.equal("location" in back, false);
    assert.equal("lat" in back, false);
  });
  it("expire après 24 h", () => {
    const stored = serializeDraft(filled, now);
    assert.equal(parseDraft(stored, now + DRAFT_MAX_AGE_MS + 1), null);
    assert.notEqual(parseDraft(stored, now + DRAFT_MAX_AGE_MS - 1), null);
  });
  it("ignore un contenu illisible ou étranger", () => {
    assert.equal(parseDraft("{pas du json", now), null);
    assert.equal(parseDraft("[]", now), null);
    assert.equal(parseDraft(null, now), null);
    const odd = parseDraft(
      JSON.stringify({ savedAt: now, when: "jamais", period: 4, date: "x" }),
      now,
    );
    assert.equal(odd?.when, "asap");
    assert.equal(odd?.period, "any");
    assert.equal(odd?.date, "");
  });
  it("sauve, restitue, efface", () => {
    const storage = memory();
    saveDraft(storage, filled, now);
    assert.ok(storage.data.has(DRAFT_KEY));
    assert.deepEqual(loadDraft(storage, now), filled);
    clearDraft(storage);
    assert.equal(loadDraft(storage, now), null);
  });
  it("un brouillon vide n'est pas stocké", () => {
    const storage = memory();
    saveDraft(storage, emptyDraft(), now);
    assert.equal(storage.data.size, 0);
  });
  it("marche sans stockage, ou avec un stockage qui lève", () => {
    assert.equal(loadDraft(undefined), null);
    saveDraft(undefined, filled);
    clearDraft(undefined);
    const broken = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("full");
      },
      removeItem: () => {
        throw new Error("blocked");
      },
    };
    assert.equal(loadDraft(broken), null);
    saveDraft(broken, filled);
    clearDraft(broken);
  });
  it("la clé d'idempotence a 22 à 64 caractères [A-Za-z0-9_-]", () => {
    assert.ok(isIdempotencyKey(newIdempotencyKey()));
    assert.equal(newIdempotencyKey().length, 32);
    assert.equal(isIdempotencyKey("trop-court"), false);
    assert.equal(isIdempotencyKey("a".repeat(65)), false);
    assert.equal(isIdempotencyKey("a".repeat(30) + "!"), false);
  });
});

describe("validateDraft et corps du POST", () => {
  const today = "2026-10-03";
  const ok = { hasLocation: false, profileComplete: true, today };
  const base: Draft = {
    ...emptyDraft(),
    tradeSlug: "plomberie",
    zoneSlug: "ouakam",
    landmark: "près de la boutique",
    description: "Fuite",
  };

  it("exige métier, quartier et repère ou position", () => {
    assert.deepEqual(validateDraft(emptyDraft(), ok), {
      trade: "trade",
      zone: "zone",
      landmark: "landmark",
      description: "description",
    });
    assert.equal(hasErrors(validateDraft(base, ok)), false);
  });
  it("la position remplace le repère", () => {
    const draft = { ...base, landmark: "" };
    assert.equal(validateDraft(draft, ok).landmark, "landmark");
    assert.equal(validateDraft(draft, { ...ok, hasLocation: true }).landmark, undefined);
  });
  it("la description est facultative si un service est choisi, sinon 3 caractères", () => {
    assert.equal(validateDraft({ ...base, description: "" }, ok).description, "description");
    assert.equal(validateDraft({ ...base, description: "ab" }, ok).description, "description");
    assert.equal(
      validateDraft({ ...base, description: "", serviceSlug: "fuite" }, ok).description,
      undefined,
    );
  });
  it("« autre quartier » exige un texte", () => {
    const other = { ...base, zoneSlug: "", otherZone: true };
    assert.equal(validateDraft(other, ok).zone, "zone");
    assert.equal(validateDraft({ ...other, zoneText: "Cité Keur Gorgui" }, ok).zone, undefined);
  });
  it("un jour précis ne peut pas être passé", () => {
    assert.equal(validateDraft({ ...base, when: "date", date: "" }, ok).date, "date");
    assert.equal(validateDraft({ ...base, when: "date", date: "2026-10-02" }, ok).date, "date");
    assert.equal(validateDraft({ ...base, when: "date", date: "2026-10-03" }, ok).date, undefined);
  });
  it("demande le nom seulement si le profil est incomplet", () => {
    assert.equal(validateDraft(base, { ...ok, profileComplete: false }).displayName, "displayName");
    assert.equal(
      validateDraft({ ...base, displayName: "Awa" }, { ...ok, profileComplete: false }).displayName,
      undefined,
    );
  });

  it("corps minimal : slug de quartier, pas de position, pas d'urgence forcée", () => {
    const body = buildRequestBody(base);
    assert.deepEqual(body, {
      trade_slug: "plomberie",
      zone_slug: "ouakam",
      landmark: "près de la boutique",
      description: "Fuite",
      preferred_when: "asap",
      preferred_period: "any",
    });
    assert.equal("location" in body, false);
    assert.equal("urgent" in body, false);
  });
  it("corps complet : service, urgence, jour et plage, position", () => {
    const body = buildRequestBody(
      {
        ...base,
        serviceSlug: "fuite",
        urgent: true,
        when: "date",
        date: "2026-10-05",
        period: "evening",
      },
      { lat: 14.72, lon: -17.49 },
    );
    assert.equal(body.service_slug, "fuite");
    assert.equal(body.urgent, true);
    assert.equal(body.preferred_date, "2026-10-05");
    assert.equal(body.preferred_period, "evening");
    assert.deepEqual(body.location, { lat: 14.72, lon: -17.49 });
  });
  it("texte libre de quartier : zone_text, jamais zone_slug", () => {
    const body = buildRequestBody({
      ...base,
      zoneSlug: "",
      otherZone: true,
      zoneText: " Keur Gorgui ",
    });
    assert.equal(body.zone_text, "Keur Gorgui");
    assert.equal("zone_slug" in body, false);
  });
  it("refuse une position hors bornes", () => {
    const body = buildRequestBody(base, { lat: 200, lon: 0 });
    assert.equal("location" in body, false);
  });
  it("après zone_ambiguous, le quartier choisi remplace le texte libre", () => {
    const next = withZoneChoice(
      {
        ...base,
        zoneSlug: "",
        otherZone: true,
        zoneText: "Mermoz",
        idempotencyKey: "k".repeat(30),
      },
      "mermoz-pyrotechnie",
    );
    assert.equal(next.zoneSlug, "mermoz-pyrotechnie");
    assert.equal(next.otherZone, false);
    assert.equal(next.zoneText, "");
    assert.equal(next.idempotencyKey, "k".repeat(30)); // même clé : rejeu côté API
    const body = buildRequestBody(next);
    assert.equal(body.zone_slug, "mermoz-pyrotechnie");
  });
});

describe("recherche hors ligne", () => {
  const trades = [
    { slug: "plomberie", name: "Plomberie", aliases: ["plombier"], services: [] },
    {
      slug: "froid-clim",
      name: "Froid et climatisation",
      aliases: ["frigoriste"],
      services: [
        {
          slug: "recharge",
          name: "Recharge de gaz",
          aliases: ["clim ne refroidit pas"],
          urgent: false,
        },
      ],
    },
    { slug: "menage", name: "Ménage", aliases: [], services: [] },
  ];
  const zones = [
    { slug: "plateau", name: "Plateau", city: "dakar", aliases: [] },
    { slug: "ouakam", name: "Ouakam", city: "dakar", aliases: ["ouakam village"] },
    { slug: "patte-d-oie", name: "Patte d'Oie", city: "dakar", aliases: [] },
  ];
  it("trouve sans accents ni majuscules, par synonyme et par service", () => {
    assert.deepEqual(
      searchTrades("MENAGE", trades).map((t) => t.slug),
      ["menage"],
    );
    assert.deepEqual(
      searchTrades("plombier", trades).map((t) => t.slug),
      ["plomberie"],
    );
    assert.deepEqual(
      searchTrades("recharge", trades).map((t) => t.slug),
      ["froid-clim"],
    );
  });
  it("requête vide : tout, dans l'ordre de l'API", () => {
    assert.deepEqual(
      searchZones("", zones).map((z) => z.slug),
      ["plateau", "ouakam", "patte-d-oie"],
    );
  });
  it("sous 3 caractères, seule l'égalité compte (règle de l'API)", () => {
    assert.deepEqual(searchZones("pa", zones), []);
    assert.deepEqual(
      searchZones("oua", zones).map((z) => z.slug),
      ["ouakam"],
    );
  });
  it("une égalité passe avant un préfixe", () => {
    const list = [
      { slug: "a", name: "Ouakam village", city: "dakar", aliases: [] },
      { slug: "b", name: "Ouakam", city: "dakar", aliases: [] },
    ];
    assert.equal(searchZones("ouakam", list)[0]?.slug, "b");
  });
});

describe("erreurs", () => {
  it("une coupure réseau n'est pas un refus", () => {
    assert.equal(describeRequestError(new TypeError("fetch failed")).code, "network");
  });
  it("zone_ambiguous porte les candidats", () => {
    const info = describeRequestError(
      new ApiError(422, {
        code: "zone_ambiguous",
        candidates: [
          { slug: "mermoz", name: "Mermoz" },
          { slug: "sacre-coeur", name: "Sacré-Cœur" },
          { slug: 3 },
        ],
      }),
    );
    assert.equal(info.code, "zone_ambiguous");
    assert.deepEqual(info.candidates, [
      { slug: "mermoz", name: "Mermoz" },
      { slug: "sacre-coeur", name: "Sacré-Cœur" },
    ]);
  });
  it("zone_ambiguous sans candidat lisible : repli sur le support", () => {
    const info = describeRequestError(new ApiError(422, { code: "zone_ambiguous" }));
    assert.equal(info.code, "generic");
    assert.equal(info.support, true);
  });
  it("trade_not_in_zone et out_of_area proposent WhatsApp", () => {
    for (const code of ["trade_not_in_zone", "out_of_area"]) {
      assert.equal(describeRequestError(new ApiError(422, { code })).support, true);
    }
  });
  it("une erreur de saisie n'envoie pas au support", () => {
    assert.equal(
      describeRequestError(new ApiError(422, { code: "description_required" })).support,
      false,
    );
  });
  it("request_rate_limited : minutes d'attente arrondies au-dessus", () => {
    const info = describeRequestError(
      new ApiError(429, { code: "request_rate_limited", retry_after: 61 }),
    );
    assert.equal(info.key, "request_rate_limited_wait");
    assert.deepEqual(info.values, { minutes: 2 });
    assert.equal(
      describeRequestError(new ApiError(429, { code: "request_rate_limited" })).key,
      "request_rate_limited",
    );
  });
  it("idempotency_key_reused demande une clé neuve", () => {
    assert.equal(
      describeRequestError(new ApiError(409, { code: "idempotency_key_reused" })).rotateKey,
      true,
    );
    assert.equal(
      describeRequestError(new ApiError(409, { code: "request_limit_reached" })).rotateKey,
      false,
    );
  });
  it("invalid nomme les champs quand l'API le fait", () => {
    assert.deepEqual(
      describeRequestError(new ApiError(400, { code: "invalid", fields: { landmark: ["x"] } }))
        .fields,
      ["landmark"],
    );
  });
  it("401 sans code : connexion", () => {
    assert.equal(describeRequestError(new ApiError(401, undefined)).login, true);
  });
  it("request_create_failed : erreur générique", () => {
    assert.equal(
      describeRequestError(new ApiError(500, { code: "request_create_failed" })).code,
      "generic",
    );
  });
  it("code inconnu : message générique avec support", () => {
    const info = describeRequestError(new ApiError(500, { code: "nouveau_code" }));
    assert.equal(info.code, "generic");
    assert.equal(info.support, true);
  });
  it("candidatesFrom tolère toute forme", () => {
    assert.deepEqual(candidatesFrom(null), []);
    assert.deepEqual(candidatesFrom({ candidates: "x" }), []);
  });

  it("chaque code a un libellé fr (aucune impasse)", () => {
    const fr = JSON.parse(
      readFileSync(new URL("../../../messages/fr.json", import.meta.url), "utf8"),
    ) as { requests: { errors: Record<string, string> } };
    const missing = REQUEST_ERROR_CODES.filter((code) => !fr.requests.errors[code]);
    assert.deepEqual(missing, []);
    assert.ok(fr.requests.errors.request_rate_limited_wait);
  });
});

describe("annulation", () => {
  it("accepte les motifs client", () => {
    for (const reason of ["changed_mind", "found_other", "price", "unavailable"]) {
      assert.equal(validateCancel(reason, ""), null);
    }
  });
  it("refuse un motif inconnu, dont ceux du pro", () => {
    assert.equal(validateCancel("too_far", ""), "reason");
    assert.equal(validateCancel("", ""), "reason");
  });
  it("« autre » exige une note de 200 caractères au plus", () => {
    assert.equal(validateCancel("other", ""), "note");
    assert.equal(validateCancel("other", "x".repeat(201)), "note");
    assert.equal(validateCancel("other", "x".repeat(200)), null);
  });
});

describe("désistement du pro", () => {
  const cancelled = (by: string, at: string) => ({
    request: "r1",
    status: "cancelled",
    cancelled_by: by,
    created_at: at,
  });
  it("vrai si la dernière réservation a été annulée par le pro ou le système", () => {
    assert.equal(
      providerWithdrew("r1", "quoted", [cancelled("pro", "2026-10-03T10:00:00Z")]),
      true,
    );
    assert.equal(
      providerWithdrew("r1", "open", [cancelled("system", "2026-10-03T10:00:00Z")]),
      true,
    );
  });
  it("faux si c'est le client, une autre demande, ou une demande qui n'a pas rouvert", () => {
    assert.equal(
      providerWithdrew("r1", "quoted", [cancelled("client", "2026-10-03T10:00:00Z")]),
      false,
    );
    assert.equal(
      providerWithdrew("r2", "quoted", [cancelled("pro", "2026-10-03T10:00:00Z")]),
      false,
    );
    assert.equal(
      providerWithdrew("r1", "booked", [cancelled("pro", "2026-10-03T10:00:00Z")]),
      false,
    );
    assert.equal(
      providerWithdrew("r1", "cancelled", [cancelled("pro", "2026-10-03T10:00:00Z")]),
      false,
    );
  });
  it("la plus récente fait foi", () => {
    assert.equal(
      providerWithdrew("r1", "quoted", [
        cancelled("pro", "2026-10-01T10:00:00Z"),
        cancelled("client", "2026-10-02T10:00:00Z"),
      ]),
      false,
    );
  });
});

describe("identifiants et curseurs", () => {
  it("isUuid", () => {
    assert.equal(isUuid("123e4567-e89b-42d3-a456-426614174000"), true);
    assert.equal(isUuid("../../etc/passwd"), false);
    assert.equal(isUuid("123"), false);
    assert.equal(isUuid(undefined), false);
  });
  it("cursorFromNext extrait le curseur de l'URL suivante", () => {
    assert.equal(cursorFromNext("http://api/api/requests/?cursor=cD0yMDI2"), "cD0yMDI2");
    assert.equal(cursorFromNext(null), null);
    assert.equal(cursorFromNext("http://api/api/requests/"), null);
  });
  it("safeCursor borne le curseur reçu dans l'URL", () => {
    assert.equal(safeCursor("cD0yMDI2LTEw"), "cD0yMDI2LTEw");
    assert.equal(safeCursor("<script>"), undefined);
    assert.equal(safeCursor("a".repeat(201)), undefined);
    assert.equal(safeCursor(undefined), undefined);
  });
});

describe("désistement signalé par cancel_reason", () => {
  it("pro_withdrew suffit, même sans cancelled_by lisible", () => {
    assert.equal(
      providerWithdrew("r1", "open", [
        {
          request: "r1",
          status: "cancelled",
          cancelled_by: "",
          cancel_reason: "pro_withdrew",
          created_at: "2026-10-03T10:00:00Z",
        },
      ]),
      true,
    );
  });
});

describe("reconcileDraft", () => {
  const trades = [
    {
      slug: "plomberie",
      name: "Plomberie",
      aliases: [],
      services: [{ slug: "fuite", name: "Fuite", aliases: [], urgent: true }],
    },
  ];
  const zones = [{ slug: "ouakam", name: "Ouakam", city: "dakar", aliases: [] }];
  it("vide ce que le catalogue ne connaît plus", () => {
    const draft = {
      ...emptyDraft(),
      tradeSlug: "disparu",
      serviceSlug: "fuite",
      zoneSlug: "ailleurs",
    };
    const out = reconcileDraft(draft, trades, zones);
    assert.deepEqual([out.tradeSlug, out.serviceSlug, out.zoneSlug], ["", "", ""]);
  });
  it("garde ce qui existe", () => {
    const draft = {
      ...emptyDraft(),
      tradeSlug: "plomberie",
      serviceSlug: "fuite",
      zoneSlug: "ouakam",
    };
    assert.deepEqual(reconcileDraft(draft, trades, zones), draft);
  });
});

describe("callAction", () => {
  const ok = { ok: true as const, data: 1 };
  it("rejoue une fois après un rafraîchissement réussi", async () => {
    let calls = 0;
    const result = await callAction(
      async () => (++calls === 1 ? { needsRefresh: true as const } : ok),
      async () => true,
    );
    assert.deepEqual(result, ok);
    assert.equal(calls, 2);
  });
  it("session perdue si le rafraîchissement échoue ou si le serveur le redemande", async () => {
    const again = async () => ({ needsRefresh: true as const });
    const failed = await callAction(again, async () => false);
    assert.equal("error" in failed && failed.error.login, true);
    const loop = await callAction(again, async () => true);
    assert.equal("error" in loop && loop.error.login, true);
  });
  it("une exception devient une erreur network", async () => {
    const result = await callAction(
      async () => {
        throw new TypeError("fetch failed");
      },
      async () => true,
    );
    assert.equal("error" in result && result.error.code, "network");
  });
});
