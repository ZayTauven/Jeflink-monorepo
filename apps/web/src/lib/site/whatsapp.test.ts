// Tests du message WhatsApp du site (spec 006) : encodage des caractères accentués et wolof,
// sauts de ligne, et aucune donnée personnelle dans l'URL produite.
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { whatsappUrl } from "../login/support.ts";
import { composeWhatsappMessage, singleLine, whatsappIntroKind } from "./whatsapp.ts";

const PRIMERS = ["Problème :", "Mon repère :"];

describe("composeWhatsappMessage", () => {
  it("introduction, ligne vide, puis une amorce par ligne", () => {
    assert.equal(
      composeWhatsappMessage("Bonjour, je cherche un pro : plomberie à Ouakam.", PRIMERS),
      "Bonjour, je cherche un pro : plomberie à Ouakam.\n\nProblème :\nMon repère :",
    );
  });

  it("variante wolof : même forme, formule sans wolof écrit par nous", () => {
    assert.equal(
      composeWhatsappMessage("Bonjour, je préfère échanger en wolof.", PRIMERS),
      "Bonjour, je préfère échanger en wolof.\n\nProblème :\nMon repère :",
    );
  });

  it("sans amorce : l'introduction seule", () => {
    assert.equal(composeWhatsappMessage("Bonjour.", []), "Bonjour.");
  });

  it("un libellé de catalogue ne peut pas ajouter de ligne", () => {
    const message = composeWhatsappMessage(
      `Bonjour, je cherche ${singleLine("Plomberie\nMon repère : 12 rue X")}.`,
      PRIMERS,
    );
    assert.equal(message.split("\n").length, 4);
  });
});

describe("lien WhatsApp prérempli", () => {
  const message = composeWhatsappMessage("Bonjour, je cherche un pro : ménage aux Ŋë çà.", PRIMERS);
  const url = whatsappUrl("221330000000", message) ?? "";

  it("é, è, ç, ŋ, ë et sauts de ligne passent l'encodage et se relisent à l'identique", () => {
    const text = new URL(url).searchParams.get("text");
    assert.equal(text, message);
    assert.ok(url.includes("%C3%A9"), "é");
    assert.ok(url.includes("%C5%8A"), "Ŋ");
    assert.ok(url.includes("%C3%AB"), "ë");
    assert.ok(url.includes("%C3%A7"), "ç");
    assert.ok(url.includes("%C3%A8"), "è (Problème)");
    assert.ok(url.includes("%0A%0A"), "ligne vide");
    assert.ok(!url.includes("\n") && !url.includes(" "));
  });

  it("ŋ minuscule : encodé en UTF-8, relu à l'identique", () => {
    const small = whatsappUrl("221330000000", composeWhatsappMessage("Jàmm ŋ", [])) ?? "";
    assert.ok(small.includes("%C5%8B"));
    assert.equal(new URL(small).searchParams.get("text"), "Jàmm ŋ");
  });

  it("aucune donnée personnelle : seulement le métier, le quartier et les amorces", () => {
    const text = new URL(url).searchParams.get("text") ?? "";
    assert.doesNotMatch(text, /\d{4,}/, "aucun numéro");
    assert.doesNotMatch(text, /@/, "aucune adresse e-mail");
    assert.doesNotMatch(text, /https?:/, "aucune URL");
    // Les amorces restent ouvertes : rien n'est prérempli à la place du client.
    for (const line of text.split("\n").slice(2)) assert.ok(line.endsWith(":"), line);
  });

  it("sans numéro de support configuré : pas de lien", () => {
    assert.equal(whatsappUrl(null, message), null);
  });
});

describe("whatsappIntroKind", () => {
  it("choisit la formule selon ce que la page sait", () => {
    assert.equal(whatsappIntroKind("plomberie", "à Ouakam"), "both");
    assert.equal(whatsappIntroKind("plomberie", ""), "trade");
    assert.equal(whatsappIntroKind(null, "à Ouakam"), "zone");
    assert.equal(whatsappIntroKind(undefined, undefined), "none");
  });
});
