// Tests du sitemap et de robots.txt (spec 006, web 10).
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { buildRobots, buildSitemap } from "./sitemap.ts";

const origin = "https://jeflink.sn";
const coverage = [
  { trade: "plombier", zone: "ouakam", indexable: true, updated_at: "2026-10-03T01:15:20Z" },
  { trade: "plombier", zone: "yoff", indexable: false, updated_at: "2026-10-04T08:00:00Z" },
  { trade: "electricien", zone: "ouakam", indexable: true, updated_at: "pas une date" },
];

describe("buildSitemap", () => {
  const urls = buildSitemap({ origin, tradeSlugs: ["plombier", "electricien"], coverage }).map(
    (entry) => entry.url,
  );

  it("pages fixes, métiers et paires indexables ; jamais /recherche ni une paire non indexable", () => {
    for (const path of ["/", "/metiers", "/a-propos", "/contact", "/devenir-pro", "/plombier", "/electricien"]) {
      assert.ok(urls.includes(`${origin}${path === "/" ? "/" : path}`), path);
    }
    assert.ok(urls.includes(`${origin}/plombier/ouakam`));
    assert.ok(urls.includes(`${origin}/electricien/ouakam`));
    assert.ok(!urls.includes(`${origin}/plombier/yoff`), "paire non indexable exclue");
    assert.ok(!urls.some((url) => url.includes("/recherche") || url.includes("/demande")));
  });

  it("lastModified : updated_at de la couverture, le plus récent pour un métier ; date illisible ignorée", () => {
    const entries = buildSitemap({ origin, tradeSlugs: ["plombier"], coverage });
    const trade = entries.find((entry) => entry.url === `${origin}/plombier`);
    assert.equal(trade?.lastModified?.toISOString(), "2026-10-04T08:00:00.000Z");
    const bad = entries.find((entry) => entry.url === `${origin}/electricien/ouakam`);
    assert.equal(bad?.lastModified, undefined);
  });

  it("catalogue vide : seulement les pages fixes", () => {
    assert.equal(buildSitemap({ origin, tradeSlugs: [], coverage: [] }).length, 5);
  });
});

describe("buildRobots", () => {
  it("non indexable : tout est interdit, aucun sitemap", () => {
    const robots = buildRobots({ indexable: false, origin });
    assert.deepEqual(robots, { rules: { userAgent: "*", disallow: "/" } });
  });

  it("indexable : pages privées exclues, sitemap annoncé", () => {
    const robots = buildRobots({ indexable: true, origin });
    assert.deepEqual(robots.rules.disallow, ["/compte", "/demande", "/connexion", "/recherche", "/api/"]);
    assert.equal(robots.sitemap, `${origin}/sitemap.xml`);
  });
});
