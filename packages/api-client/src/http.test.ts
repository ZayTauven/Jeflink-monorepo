// Tests de jeflinkFetch (spec 001, packages/api-client tâche 1) : node:test, sans dépendance.
import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";

import {
  ApiError,
  type Transport,
  configureApiClient,
  jeflinkFetch,
  resetApiClientSession,
} from "./http.ts";

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

  it("transport serveur : ni jeton, ni langue, ni refresh du singleton (I7)", async () => {
    let read = 0;
    configureApiClient({
      baseUrl: "https://ne-pas-utiliser.test",
      getAccessToken: () => {
        read += 1;
        return "SINGLETON";
      },
      getLanguage: () => {
        read += 1;
        return "wo";
      },
      onUnauthorized: async () => {
        read += 1;
        return true;
      },
    });
    const seen: Array<{ path: string; headers: Headers }> = [];
    const transport: Transport = async (path, init) => {
      seen.push({ path, headers: new Headers(init.headers) });
      return json(401, { code: "token_expired" })();
    };
    await assert.rejects(jeflinkFetch("/api/me/", { transport }), ApiError);
    assert.equal(read, 0);
    assert.equal(calls.length, 0);
    assert.equal(seen.length, 1);
    assert.equal(seen[0]?.path, "/api/me/");
    assert.equal(seen[0]?.headers.get("Authorization"), null);
    assert.equal(seen[0]?.headers.get("Accept-Language"), null);
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

  it("pas de rejeu sous un autre compte : session changée pendant le refresh (M11)", async () => {
    let token = "COMPTE_A";
    configureApiClient({
      baseUrl: "",
      getAccessToken: () => token,
      onUnauthorized: async () => {
        // Déconnexion puis connexion d'un autre compte pendant le refresh.
        resetApiClientSession();
        token = "COMPTE_B";
        return true;
      },
    });
    responses.push(json(401, { code: "token_expired" }));
    await assert.rejects(jeflinkFetch("/api/me/", { method: "DELETE" }), ApiError);
    assert.equal(calls.length, 1);
  });

  it("un refresh terminé n'efface pas celui lancé depuis (M11)", async () => {
    let refreshes = 0;
    const releases: Array<(value: boolean) => void> = [];
    configureApiClient({
      baseUrl: "",
      getAccessToken: () => "T",
      onUnauthorized: () => {
        refreshes += 1;
        return new Promise<boolean>((resolve) => releases.push(resolve));
      },
    });
    responses.push(json(401, {}));
    const first = jeflinkFetch("/api/a/");
    await new Promise((resolve) => setTimeout(resolve, 5));
    resetApiClientSession(); // le refresh en cours n'est plus partagé
    responses.push(json(401, {}), json(401, {}));
    const second = jeflinkFetch("/api/b/");
    const third = jeflinkFetch("/api/c/");
    await new Promise((resolve) => setTimeout(resolve, 5));
    releases[0]?.(false); // fin du premier : ne doit pas libérer le second
    await assert.rejects(first, ApiError);
    responses.push(json(401, {}));
    const fourth = jeflinkFetch("/api/d/"); // doit attendre le second refresh, pas en lancer un
    await new Promise((resolve) => setTimeout(resolve, 5));
    assert.equal(refreshes, 2);
    responses.push(json(200, {}), json(200, {}), json(200, {}));
    releases[1]?.(true);
    await Promise.all([second, third, fourth]);
    assert.equal(refreshes, 2);
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

describe("chemins piégés (revue BFF, I-C)", () => {
  it("un paramètre de chemin qui change d'endpoint n'est jamais envoyé", async () => {
    configureApiClient({ baseUrl: "" });
    for (const url of [
      "/api/ops/accounts/../../me/sessions/revoke-others/",
      "/api/ops/accounts/..%2F..%2Fme%2Fsessions%2F/",
      "/api/ops/accounts/%2e%2e/x/",
      "/api/a\\b/",
    ]) {
      await assert.rejects(jeflinkFetch(url, { method: "POST" }), (error: unknown) => {
        assert.ok(error instanceof ApiError);
        assert.equal(error.code, "unsafe_path");
        return true;
      });
    }
    assert.equal(calls.length, 0);
    responses.push(json(200, {}));
    await jeflinkFetch("/api/ops/accounts/?q=..%2F");
    assert.equal(calls.length, 1);
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
