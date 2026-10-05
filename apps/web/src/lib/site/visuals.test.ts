// Tests du registre des visuels (spec 006, web 4) : par `icon_key`, jamais par slug ; un
// `icon_key` absent ou inconnu prend le visuel générique ; chaque fichier référencé existe.
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { describe, it } from "node:test";

import { GENERIC_VISUAL, SITE_IMAGES, tradeVisual } from "./visuals.ts";

const PUBLIC = new URL("../../../public/", import.meta.url);
const fr = JSON.parse(
  readFileSync(new URL("../../../messages/fr.json", import.meta.url), "utf8"),
) as { site: { visuals: Record<string, string> } };

const PHOTO_KEYS = ["plumbing", "electricity", "cooling", "cleaning", "handyman"];

describe("tradeVisual", () => {
  it("icon_key connus : une photo, avec sa clé d'alt en i18n", () => {
    for (const key of PHOTO_KEYS) {
      const visual = tradeVisual(key);
      assert.equal(visual.kind, "photo", key);
      if (visual.kind === "photo") assert.ok(fr.site.visuals[visual.altKey], `alt ${key}`);
    }
  });

  it("absent, inconnu ou piégé : générique, jamais d'erreur", () => {
    for (const key of [
      null,
      undefined,
      "",
      "appliance",
      "nouveau-metier",
      "__proto__",
      "toString",
    ]) {
      assert.equal(tradeVisual(key), GENERIC_VISUAL, String(key));
    }
  });

  it("chaque fichier référencé existe", () => {
    const files = [
      ...PHOTO_KEYS.flatMap((key) => {
        const visual = tradeVisual(key);
        return visual.kind === "photo" ? [visual.card, visual.compact] : [];
      }),
      SITE_IMAGES.hero.small,
      SITE_IMAGES.hero.large,
      SITE_IMAGES.pro.image,
      SITE_IMAGES.dakar.image,
    ];
    for (const file of files) {
      assert.ok(existsSync(new URL(file.src.replace(/^\//, ""), PUBLIC)), file.src);
      assert.ok(file.width > 0 && file.height > 0);
    }
    for (const image of [SITE_IMAGES.hero, SITE_IMAGES.pro, SITE_IMAGES.dakar]) {
      assert.ok(fr.site.visuals[image.altKey], image.altKey);
    }
  });
});
