// Tests de la session navigateur (spec 001, web / console 1) : verrou entre onglets, délais,
// codes d'échec, déconnexion.
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { REFRESH_ENDPOINT, REFRESH_LOCK } from "./bff/paths.ts";
import {
  REFRESHED_AT_KEY,
  type WebSessionDeps,
  logoutWebSession,
  refreshWebSession,
} from "./web.ts";

type Call = { url: string; init: RequestInit | undefined };

/** Verrou exclusif en mémoire, partagé comme le serait navigator.locks entre onglets. */
function memoryLocks(names: string[] = []) {
  const tails = new Map<string, Promise<unknown>>();
  return {
    request<T>(
      name: string,
      options: { signal: AbortSignal },
      callback: () => Promise<T>,
    ): Promise<T> {
      names.push(name);
      const previous = tails.get(name) ?? Promise.resolve();
      const result = new Promise<T>((resolve, reject) => {
        options.signal.addEventListener("abort", () => reject(options.signal.reason), {
          once: true,
        });
        previous.then(
          () => (options.signal.aborted ? undefined : callback().then(resolve, reject)),
          reject,
        );
      });
      tails.set(
        name,
        result.catch(() => undefined),
      );
      return result;
    },
  };
}

function memoryStorage() {
  const values = new Map<string, string>();
  return {
    values,
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => void values.set(key, value),
  };
}

function setup(respond: () => Promise<Response>, overrides: Partial<WebSessionDeps> = {}) {
  const calls: Call[] = [];
  const messages: unknown[] = [];
  const resets: number[] = [];
  let clock = 1_000;
  const deps: WebSessionDeps = {
    fetch: (async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(input), init });
      return respond();
    }) as typeof fetch,
    locks: memoryLocks(),
    storage: memoryStorage(),
    now: () => (clock += 1),
    timeoutMs: 1_000,
    openChannel: () => ({
      postMessage: (message: unknown) => void messages.push(message),
      close: () => undefined,
    }),
    resetSession: () => void resets.push(1),
    ...overrides,
  };
  return { deps, calls, messages, resets };
}

const status = (code: number) => async () => new Response(null, { status: code });

describe("refreshWebSession", () => {
  it("fait un POST au BFF, avec X-Requested-With et un délai, sous le verrou partagé", async () => {
    const names: string[] = [];
    const storage = memoryStorage();
    const { deps, calls, resets } = setup(status(200), { locks: memoryLocks(names), storage });
    assert.equal(await refreshWebSession(deps), true);
    assert.deepEqual(names, [REFRESH_LOCK]);
    assert.equal(calls.length, 1);
    assert.equal(calls[0]?.url, REFRESH_ENDPOINT);
    assert.equal(calls[0]?.init?.method, "POST");
    assert.equal(new Headers(calls[0]?.init?.headers).get("x-requested-with"), "jeflink");
    assert.equal(calls[0]?.init?.credentials, "same-origin");
    assert.equal(calls[0]?.init?.cache, "no-store");
    assert.ok(calls[0]?.init?.signal instanceof AbortSignal);
    assert.ok(storage.values.get(REFRESHED_AT_KEY));
    assert.equal(resets.length, 0);
  });

  it("sur un 401 : false, client remis à zéro, autres onglets prévenus", async () => {
    const storage = memoryStorage();
    const { deps, resets, messages } = setup(status(401), { storage });
    assert.equal(await refreshWebSession(deps), false);
    assert.equal(resets.length, 1);
    assert.deepEqual(messages, [{ type: "session-ended", reason: "expired" }]);
    assert.equal(storage.values.has(REFRESHED_AT_KEY), false);
  });

  for (const code of [429, 502]) {
    it(`sur un ${code} : false, sans fin de session`, async () => {
      const storage = memoryStorage();
      const { deps, resets, messages } = setup(status(code), { storage });
      assert.equal(await refreshWebSession(deps), false);
      assert.equal(resets.length, 0);
      assert.equal(messages.length, 0);
      assert.equal(storage.values.has(REFRESHED_AT_KEY), false);
    });
  }

  it("renvoie false sur une coupure réseau ou un délai dépassé", async () => {
    const { deps, resets } = setup(async () => {
      throw new DOMException("The operation timed out.", "TimeoutError");
    });
    assert.equal(await refreshWebSession(deps), false);
    assert.equal(resets.length, 0);
  });

  it("verrou tenu trop longtemps par un autre onglet : false, sans appel", async () => {
    const locks = memoryLocks();
    void locks.request(
      REFRESH_LOCK,
      { signal: new AbortController().signal },
      () => new Promise<void>(() => undefined),
    );
    const { deps, calls } = setup(status(200), { locks, timeoutMs: 20 });
    // AbortSignal.timeout ne retient pas la boucle d'événements : un minuteur la garde active.
    const keepAlive = setTimeout(() => undefined, 1_000);
    try {
      assert.equal(await refreshWebSession(deps), false);
    } finally {
      clearTimeout(keepAlive);
    }
    assert.equal(calls.length, 0);
  });

  it("deux onglets en même temps : un seul refresh, les deux repartent", async () => {
    let release: (value: Response) => void = () => undefined;
    const pending = new Promise<Response>((resolve) => (release = resolve));
    const { deps, calls } = setup(() => pending);
    const first = refreshWebSession(deps);
    const second = refreshWebSession(deps);
    release(new Response(null, { status: 200 }));
    assert.deepEqual(await Promise.all([first, second]), [true, true]);
    assert.equal(calls.length, 1);
  });

  it("marque jf-refreshed-at dans le futur : ignorée, le refresh part vraiment", async () => {
    const storage = memoryStorage();
    storage.setItem(REFRESHED_AT_KEY, String(10_000_000_000_000));
    const { deps, calls } = setup(status(200), { storage });
    assert.equal(await refreshWebSession(deps), true);
    assert.equal(calls.length, 1);
    assert.ok(Number(storage.values.get(REFRESHED_AT_KEY)) < 10_000_000_000_000);
  });

  it("un refresh échoué dans un onglet n'empêche pas l'autre d'essayer", async () => {
    const codes = [503, 200];
    const { deps, calls } = setup(async () => new Response(null, { status: codes.shift() ?? 500 }));
    assert.deepEqual(await Promise.all([refreshWebSession(deps), refreshWebSession(deps)]), [
      false,
      true,
    ]);
    assert.equal(calls.length, 2);
  });

  it("sans Web Locks ni stockage : refresh direct", async () => {
    const throwing = {
      getItem: () => {
        throw new Error("bloqué");
      },
      setItem: () => {
        throw new Error("bloqué");
      },
    };
    const { deps, calls } = setup(status(200), { locks: undefined, storage: throwing });
    assert.equal(await refreshWebSession(deps), true);
    assert.equal(calls.length, 1);
  });
});

describe("logoutWebSession", () => {
  it("POST de déconnexion sous le verrou, puis fin de session annoncée", async () => {
    const names: string[] = [];
    const { deps, calls, resets, messages } = setup(status(204), { locks: memoryLocks(names) });
    assert.equal(await logoutWebSession(deps), true);
    assert.deepEqual(names, [REFRESH_LOCK]);
    assert.equal(calls[0]?.url, "/api/auth/logout/");
    assert.equal(calls[0]?.init?.method, "POST");
    assert.equal(new Headers(calls[0]?.init?.headers).get("x-requested-with"), "jeflink");
    assert.equal(resets.length, 1);
    assert.deepEqual(messages, [{ type: "session-ended", reason: "logout" }]);
  });

  it("attend la fin d'un refresh en cours avant de déconnecter", async () => {
    let release: (value: Response) => void = () => undefined;
    const pending = new Promise<Response>((resolve) => (release = resolve));
    const order: string[] = [];
    const { deps } = setup(async () => new Response(null, { status: 204 }));
    deps.fetch = (async (input: RequestInfo | URL) => {
      order.push(String(input));
      return String(input) === REFRESH_ENDPOINT ? pending : new Response(null, { status: 204 });
    }) as typeof fetch;
    const refreshing = refreshWebSession(deps);
    const loggingOut = logoutWebSession(deps);
    await new Promise((resolve) => setTimeout(resolve, 5));
    assert.deepEqual(order, [REFRESH_ENDPOINT]);
    release(new Response(null, { status: 200 }));
    await Promise.all([refreshing, loggingOut]);
    assert.deepEqual(order, [REFRESH_ENDPOINT, "/api/auth/logout/"]);
  });

  it("BFF injoignable : false, la session n'est pas déclarée finie", async () => {
    const { deps, resets, messages } = setup(async () => {
      throw new TypeError("Failed to fetch");
    });
    assert.equal(await logoutWebSession(deps), false);
    assert.equal(resets.length, 0);
    assert.equal(messages.length, 0);
  });
});
