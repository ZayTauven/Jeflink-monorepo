// Tests des messages transmis au navigateur par les pages publiques (spec 006, web 1) : seuls les
// îlots client en reçoivent ; aucun texte de l'espace client ne part avec une page publique.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

import { type Messages, pickMessages, SITE_CLIENT_NAMESPACES } from "./client-messages.ts";

const fr = JSON.parse(
  readFileSync(new URL("../../messages/fr.json", import.meta.url), "utf8"),
) as Messages;

function keys(node: string | Messages, prefix = ""): string[] {
  if (typeof node === "string") return [prefix];
  return Object.entries(node).flatMap(([key, value]) =>
    keys(value, prefix ? `${prefix}.${key}` : key),
  );
}

describe("pickMessages", () => {
  it("garde seulement les espaces demandés, avec leur arborescence", () => {
    const picked = pickMessages({ a: { b: { c: "1", d: "2" }, e: "3" }, f: "4" }, ["a.b", "f"]);
    assert.deepEqual(picked, { a: { b: { c: "1", d: "2" } }, f: "4" });
  });

  it("fusionne deux espaces voisins, ignore un chemin absent", () => {
    const picked = pickMessages({ a: { b: "1", c: "2" } }, ["a.b", "a.c", "a.x.y"]);
    assert.deepEqual(picked, { a: { b: "1", c: "2" } });
  });
});

describe("payload d'une page publique", () => {
  const payload = pickMessages(fr, SITE_CLIENT_NAMESPACES);
  const sent = keys(payload);

  it("contient les messages des îlots (menu, bandeau)", () => {
    assert.ok(sent.includes("site.menu.open"));
    assert.ok(sent.includes("site.marquee.pause"));
  });

  it("aucune clé requests.*, bookings.*, connexion.* ni catalog.*", () => {
    for (const forbidden of ["requests.", "bookings.", "connexion.", "catalog."]) {
      assert.ok(!sent.some((key) => key.startsWith(forbidden)), forbidden);
    }
    assert.ok(!("requests" in payload) && !("bookings" in payload));
  });

  it("reste petit : une fraction de fr.json, jamais l'espace client", () => {
    assert.ok(JSON.stringify(payload).length < 1000);
    assert.ok(JSON.stringify(payload).length < JSON.stringify(fr).length / 20);
  });

  it("les espaces des îlots existent dans fr.json", () => {
    for (const namespace of SITE_CLIENT_NAMESPACES) {
      assert.ok(
        sent.some((key) => key.startsWith(`${namespace}.`)),
        namespace,
      );
    }
  });
});
