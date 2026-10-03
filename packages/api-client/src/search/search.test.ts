// Mêmes vecteurs que `jeflink.common.search` (spec 002) : le Python fait foi.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";

import { matchSearch, normalizeSearch } from "./index.ts";

type Vectors = {
  normalize: [string, string][];
  match: { query: string; terms: string[]; rank: number | null }[];
};

const vectors = JSON.parse(
  readFileSync(
    new URL("../../../../apps/api/jeflink/common/tests/search_vectors.json", import.meta.url),
    "utf8",
  ),
) as Vectors;

describe("normalizeSearch", () => {
  for (const [text, expected] of vectors.normalize) {
    it(JSON.stringify(text), () => assert.equal(normalizeSearch(text), expected));
  }
});

describe("matchSearch", () => {
  for (const { query, terms, rank } of vectors.match) {
    it(JSON.stringify(query), () => assert.equal(matchSearch(query, terms), rank));
  }
});
