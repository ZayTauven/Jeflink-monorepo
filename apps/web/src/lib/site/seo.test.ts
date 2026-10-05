// Tests des métadonnées du site public (spec 006, web 10).
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { DESCRIPTION_MAX, OG_DESCRIPTION_MAX, TITLE_MAX, pageMetadata, truncate } from "./seo.ts";

const base = {
  title: "Plombier à Ouakam",
  fullTitle: "Plombier à Ouakam · Jeflink",
  description: "Plombier à Ouakam avec des pros vérifiés.",
  path: "/plombier/ouakam",
  siteName: "Jeflink",
  locale: "fr_SN",
};

describe("truncate", () => {
  it("texte court : inchangé ; long : au dernier mot, avec « … », dans la limite", () => {
    assert.equal(truncate("Bonjour le monde", 60), "Bonjour le monde");
    const long = "mot ".repeat(80);
    const cut = truncate(long, 100);
    assert.ok(cut.length <= 100 && cut.endsWith("…"));
    assert.ok(!cut.includes("mo…"), "pas de mot coupé");
  });
});

describe("pageMetadata", () => {
  it("canonical, Open Graph, fr_SN, limites de longueur", () => {
    const meta = pageMetadata({
      ...base,
      fullTitle: "T".repeat(100),
      description: "d ".repeat(200),
    });
    assert.equal(meta.alternates?.canonical, "/plombier/ouakam");
    assert.equal(meta.openGraph?.url, "/plombier/ouakam");
    assert.equal((meta.openGraph as { locale: string }).locale, "fr_SN");
    assert.equal((meta.openGraph as { siteName: string }).siteName, "Jeflink");
    assert.ok(((meta.title as { absolute: string }).absolute).length <= TITLE_MAX);
    assert.ok((meta.description ?? "").length <= DESCRIPTION_MAX);
    assert.ok(((meta.openGraph as { description: string }).description).length <= OG_DESCRIPTION_MAX);
  });

  it("indexable par défaut ; non indexable : noindex, follow, canonical vers elle-même", () => {
    assert.equal(pageMetadata(base).robots, undefined);
    assert.equal(pageMetadata({ ...base, indexable: true }).robots, undefined);
    const meta = pageMetadata({ ...base, indexable: false });
    assert.deepEqual(meta.robots, { index: false, follow: true });
    assert.equal(meta.alternates?.canonical, "/plombier/ouakam");
  });
});
