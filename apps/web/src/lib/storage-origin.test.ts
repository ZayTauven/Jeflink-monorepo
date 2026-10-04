// Tests de l'origine du stockage des photos (spec 004, web 2).
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { storageOrigin } from "./storage-origin.ts";

describe("storageOrigin", () => {
  it("garde l'origine seule, sans chemin ni signature", () => {
    assert.equal(
      storageOrigin({
        NODE_ENV: "production",
        STORAGE_PUBLIC_ORIGIN: "https://s3.jeflink.sn/b/x?y=1",
      }),
      "https://s3.jeflink.sn",
    );
  });
  it("vide : rien en production, le stockage local en dev", () => {
    assert.equal(storageOrigin({ NODE_ENV: "production" }), null);
    assert.equal(storageOrigin({ NODE_ENV: "development" }), "http://localhost:8333");
  });
  it("refuse http en production et tout autre schéma", () => {
    assert.equal(
      storageOrigin({ NODE_ENV: "production", STORAGE_PUBLIC_ORIGIN: "http://s3.x" }),
      null,
    );
    assert.equal(
      storageOrigin({ NODE_ENV: "development", STORAGE_PUBLIC_ORIGIN: "http://localhost:9000" }),
      "http://localhost:9000",
    );
    assert.equal(
      storageOrigin({ NODE_ENV: "development", STORAGE_PUBLIC_ORIGIN: "javascript:alert(1)" }),
      null,
    );
    assert.equal(
      storageOrigin({ NODE_ENV: "production", STORAGE_PUBLIC_ORIGIN: "pas une url" }),
      null,
    );
  });
});
