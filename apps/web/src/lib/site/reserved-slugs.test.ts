// Slugs réservés (spec 006, ADR 0013) : chaque segment de premier niveau de `src/app` doit figurer
// dans le JSON partagé avec Django, pour qu'un métier ne masque jamais une page ni un fichier de
// Next. Les groupes `(site)` et `(espace)` ne comptent pas (ils n'ajoutent pas de segment).
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

const APP = fileURLToPath(new URL("../../app/", import.meta.url));
const RESERVED = JSON.parse(
  readFileSync(
    fileURLToPath(
      new URL("../../../../api/jeflink/catalog/reserved_slugs.json", import.meta.url),
    ),
    "utf8",
  ),
) as { trade_slugs: string[]; zone_slugs: string[] };

/** Fichiers de métadonnées de Next qui occupent un nom d'URL (`/sitemap.xml`, `/icon`…). */
const METADATA_FILES = new Set([
  "sitemap",
  "robots",
  "manifest",
  "icon",
  "apple-icon",
  "opengraph-image",
  "twitter-image",
]);

/** Segments d'URL de premier niveau : dossiers publics et fichiers de métadonnées. */
function topLevelSegments(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    const isDir = statSync(full).isDirectory();
    if (isDir && /^\(.+\)$/.test(name)) {
      out.push(...topLevelSegments(full)); // groupe de routes : transparent
    } else if (isDir) {
      if (name.startsWith("_") || name.startsWith("[")) continue; // privé ou dynamique
      out.push(name);
    } else {
      const base = name.replace(/\.[^.]+$/, "");
      if (METADATA_FILES.has(base)) out.push(base);
    }
  }
  return out;
}

describe("slugs réservés", () => {
  const segments = topLevelSegments(APP);

  it("des segments existent (le test lit bien src/app)", () => {
    for (const expected of ["a-propos", "contact", "devenir-pro", "compte", "connexion", "demande", "api"]) {
      assert.ok(segments.includes(expected), expected);
    }
  });

  it("chaque segment de premier niveau figure dans trade_slugs", () => {
    for (const segment of segments) {
      assert.ok(RESERVED.trade_slugs.includes(segment), `« ${segment} » absent de reserved_slugs.json`);
    }
  });

  it("les noms de fichiers de métadonnées sont aussi réservés pour les quartiers", () => {
    for (const name of ["opengraph-image", "twitter-image"]) {
      assert.ok(RESERVED.zone_slugs.includes(name), name);
    }
  });
});
