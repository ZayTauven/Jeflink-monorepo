// Tests de jeflinkFetch (spec 001, packages/api-client tâche 1) : node:test, sans dépendance.
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";

import { ApiError, configureApiClient, jeflinkFetch } from "./http.ts";

type Call = { url: string; headers: Headers; credentials: RequestCredentials | undefined };

let calls: Call[];
let responses: Array<() => Response>;
const realFetch = globalThis.fetch;

function json(status: number, body: unknown): () => Response {
  return () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
}

beforeEach(() => {
  calls = [];
  responses = [];
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({
      url: String(input),
      headers: new Headers(init?.headers),
      credentials: init?.credentials,
    });
    const next = responses.shift();
    assert.ok(next, "réponse inattendue");
    return next();
  }) as typeof fetch;
});

afterEach(() => {
  globalThis.fetch = realFetch;
});

describe("en-têtes", () => {
  it("envoie X-Requested-With, la langue et le jeton de la configuration", async () => {
    configureApiClient({
      baseUrl: "https://api.test",
      getAccessToken: () => "A1",
      getLanguage: () => "wo",
    });
    responses.push(json(200, { ok: true }));
    const result = await jeflinkFetch<{ data: unknown; status: number }>("/api/me/");
    assert.equal(result.status, 200);
    const [call] = calls;
    assert.equal(call?.url, "https://api.test/api/me/");
    assert.equal(call?.headers.get("X-Requested-With"), "jeflink");
    assert.equal(call?.headers.get("Accept-Language"), "wo");
    assert.equal(call?.headers.get("Authorization"), "Bearer A1");
    assert.equal(call?.credentials, "omit");
  });

  it("le jeton passé à l'appel est prioritaire (côté serveur, jamais le singleton)", async () => {
    configureApiClient({ baseUrl: "", getAccessToken: () => "SINGLETON" });
    responses.push(json(200, {}));
    await jeflinkFetch("/api/me/", { accessToken: "PAR_APPEL" });
    assert.equal(calls[0]?.headers.get("Authorization"), "Bearer PAR_APPEL");
  });

  it("sans jeton (web, console) : cookies du BFF, pas d'Authorization", async () => {
    configureApiClient({ baseUrl: "" });
    responses.push(json(200, {}));
    await jeflinkFetch("/api/me/");
    assert.equal(calls[0]?.headers.get("Authorization"), null);
    assert.equal(calls[0]?.credentials, "include");
  });
});

describe("401 et rafraîchissement", () => {
  it("un refresh puis un seul rejeu avec le nouveau jeton", async () => {
    let token = "OLD";
    let refreshes = 0;
    configureApiClient({
      baseUrl: "",
      getAccessToken: () => token,
      onUnauthorized: async () => {
        refreshes += 1;
        token = "NEW";
        return true;
      },
    });
    responses.push(json(401, { code: "token_expired" }), json(200, { ok: true }));
    await jeflinkFetch("/api/me/");
    assert.equal(refreshes, 1);
    assert.deepEqual(
      calls.map((c) => c.headers.get("Authorization")),
      ["Bearer OLD", "Bearer NEW"],
    );
  });

  it("401 simultanés : un seul refresh partagé", async () => {
    let token = "OLD";
    let refreshes = 0;
    let release: (value: boolean) => void = () => {};
    configureApiClient({
      baseUrl: "",
      getAccessToken: () => token,
      onUnauthorized: () => {
        refreshes += 1;
        return new Promise<boolean>((resolve) => {
          release = (value) => {
            token = "NEW";
            resolve(value);
          };
        });
      },
    });
    responses.push(json(401, {}), json(401, {}), json(200, { a: 1 }), json(200, { b: 2 }));
    const both = Promise.all([jeflinkFetch("/api/a/"), jeflinkFetch("/api/b/")]);
    await new Promise((resolve) => setTimeout(resolve, 10));
    release(true);
    await both;
    assert.equal(refreshes, 1);
  });

  it("refresh refusé : l'erreur 401 d'origine remonte, sans rejeu", async () => {
    configureApiClient({
      baseUrl: "",
      getAccessToken: () => "T",
      onUnauthorized: async () => false,
    });
    responses.push(json(401, { code: "session_revoked" }));
    await assert.rejects(jeflinkFetch("/api/me/"), (error: unknown) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.code, "session_revoked");
      return true;
    });
    assert.equal(calls.length, 1);
  });

  it("pas de boucle : un second 401 après le rejeu remonte", async () => {
    let refreshes = 0;
    configureApiClient({
      baseUrl: "",
      getAccessToken: () => "T",
      onUnauthorized: async () => {
        refreshes += 1;
        return true;
      },
    });
    responses.push(json(401, {}), json(401, { code: "token_invalid" }));
    await assert.rejects(jeflinkFetch("/api/me/"), ApiError);
    assert.equal(refreshes, 1);
    assert.equal(calls.length, 2);
  });

  it("jeton passé à l'appel : jamais de refresh automatique (BFF)", async () => {
    let refreshes = 0;
    configureApiClient({
      baseUrl: "",
      onUnauthorized: async () => {
        refreshes += 1;
        return true;
      },
    });
    responses.push(json(401, { code: "token_expired" }));
    await assert.rejects(jeflinkFetch("/api/me/", { accessToken: "T" }), ApiError);
    assert.equal(refreshes, 0);
  });

  it("une erreur du refresh vaut un refus", async () => {
    configureApiClient({
      baseUrl: "",
      getAccessToken: () => "T",
      onUnauthorized: async () => {
        throw new Error("réseau coupé");
      },
    });
    responses.push(json(401, {}));
    await assert.rejects(jeflinkFetch("/api/me/"), ApiError);
  });
});

describe("corps de réponse", () => {
  it("garde le texte brut d'une page HTML de proxy", async () => {
    configureApiClient({ baseUrl: "" });
    responses.push(() => new Response("<html>502</html>", { status: 502 }));
    await assert.rejects(jeflinkFetch("/api/me/"), (error: unknown) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.body, "<html>502</html>");
      return true;
    });
  });
});
