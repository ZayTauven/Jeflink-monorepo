// Session côté navigateur (web, console) : refresh branché sur `onUnauthorized` de
// configureApiClient, et déconnexion (spec 001, « BFF Next », S6). Le refresh tourne à chaque
// usage : deux refresh concurrents, même dans deux onglets, s'annuleraient. Le verrou Web Locks
// `jf-refresh` est partagé avec la page de rebond du BFF et pris aussi par la déconnexion (un
// refresh ne peut pas croiser une révocation). Un onglet qui obtient le verrou après un refresh
// réussi ailleurs ne recommence pas.
//
// Sans Web Locks (navigateur très ancien), l'appel part sans verrou, comme dans la page de
// rebond : la grâce d'une fois par rotation (Q15) couvre un refresh concurrent.

import { REFRESHED_AT_KEY, REFRESH_ENDPOINT, REFRESH_LOCK } from "./bff/paths.ts";
import { resetApiClientSession } from "./http.ts";

export { REFRESHED_AT_KEY };
/** Canal des autres onglets : la session de cet appareil est finie. */
export const SESSION_CHANNEL = "jf-session";
const LOGOUT_ENDPOINT = "/api/auth/logout/";
const TIMEOUT_MS = 20_000;

type Storage = Pick<globalThis.Storage, "getItem" | "setItem">;
type Locks = {
  request<T>(
    name: string,
    options: { signal: AbortSignal },
    callback: () => Promise<T>,
  ): Promise<T>;
};
type Channel = Pick<BroadcastChannel, "postMessage" | "close">;
export type SessionEndReason = "logout" | "expired";

export type WebSessionDeps = {
  fetch: typeof globalThis.fetch;
  locks: Locks | undefined;
  storage: Storage | undefined;
  now: () => number;
  /** Délai du fetch, et délai d'attente du verrou (même valeur). */
  timeoutMs: number;
  openChannel: (() => Channel) | undefined;
  resetSession: () => void;
};

function browserDeps(): WebSessionDeps {
  let storage: Storage | undefined;
  try {
    storage = globalThis.localStorage;
  } catch {
    storage = undefined; // stockage bloqué (navigation privée, réglages du navigateur)
  }
  const locks = typeof navigator !== "undefined" ? navigator.locks : undefined;
  return {
    fetch: (...args) => globalThis.fetch(...args),
    locks: locks && typeof locks.request === "function" ? (locks as Locks) : undefined,
    storage,
    now: () => Date.now(),
    timeoutMs: TIMEOUT_MS,
    openChannel:
      typeof BroadcastChannel === "function"
        ? () => new BroadcastChannel(SESSION_CHANNEL)
        : undefined,
    resetSession: resetApiClientSession,
  };
}

function refreshedAt(storage: Storage | undefined): number {
  try {
    return Number(storage?.getItem(REFRESHED_AT_KEY) ?? 0) || 0;
  } catch {
    return 0;
  }
}

/** Appel sous le verrou partagé ; `false` si le verrou n'est pas obtenu à temps. */
async function underLock(deps: WebSessionDeps, run: () => Promise<boolean>): Promise<boolean> {
  if (!deps.locks) return run();
  try {
    return await deps.locks.request(
      REFRESH_LOCK,
      { signal: AbortSignal.timeout(deps.timeoutMs) },
      run,
    );
  } catch {
    return false; // verrou tenu trop longtemps par un autre onglet : on n'attend pas sans fin
  }
}

async function post(deps: WebSessionDeps, path: string): Promise<Response | null> {
  try {
    return await deps.fetch(path, {
      method: "POST",
      headers: { "X-Requested-With": "jeflink" },
      credentials: "same-origin",
      cache: "no-store",
      signal: AbortSignal.timeout(deps.timeoutMs),
    });
  } catch {
    return null; // coupure réseau ou délai dépassé
  }
}

/** Fin de session : plus aucun rejeu sous ce compte ici, et les autres onglets sont prévenus. */
function endSession(deps: WebSessionDeps, reason: SessionEndReason): void {
  deps.resetSession();
  try {
    const channel = deps.openChannel?.();
    channel?.postMessage({ type: "session-ended", reason });
    channel?.close();
  } catch {
    // canal indisponible : les autres onglets le verront à leur prochain 401
  }
}

/**
 * Rafraîchit la session par le BFF. `true` : l'accès est neuf, la requête peut être rejouée.
 * `false` : session finie (401, et le client est remis à zéro), limite atteinte (429), panne
 * ou délai dépassé ; un 429 ou une panne ne déconnectent jamais (le BFF n'efface rien).
 */
export function refreshWebSession(deps: WebSessionDeps = browserDeps()): Promise<boolean> {
  const startedAt = deps.now();
  return underLock(deps, async () => {
    // Un autre onglet a rafraîchi pendant l'attente du verrou : le cookie d'accès est déjà neuf.
    if (refreshedAt(deps.storage) >= startedAt) return true;
    const response = await post(deps, REFRESH_ENDPOINT);
    if (!response) return false;
    if (response.status === 401) {
      endSession(deps, "expired");
      return false;
    }
    if (!response.ok) return false;
    try {
      deps.storage?.setItem(REFRESHED_AT_KEY, String(deps.now()));
    } catch {
      // stockage plein ou bloqué : seul l'évitement d'un second refresh est perdu
    }
    return true;
  });
}

/**
 * Déconnexion de cet appareil, sous le verrou du refresh. `false` : le BFF n'a pas répondu, les
 * cookies sont peut-être encore là ; l'interface propose de réessayer.
 */
export function logoutWebSession(deps: WebSessionDeps = browserDeps()): Promise<boolean> {
  return underLock(deps, async () => {
    const response = await post(deps, LOGOUT_ENDPOINT);
    if (!response?.ok) return false;
    endSession(deps, "logout");
    return true;
  });
}

/** Écoute la fin de session annoncée par un autre onglet. Renvoie la fonction de désabonnement. */
export function onWebSessionEnded(listener: (reason: SessionEndReason) => void): () => void {
  if (typeof BroadcastChannel !== "function") return () => undefined;
  const channel = new BroadcastChannel(SESSION_CHANNEL);
  channel.onmessage = (event: MessageEvent<unknown>) => {
    const data = event.data as { type?: unknown; reason?: unknown } | null;
    if (data?.type !== "session-ended") return;
    resetApiClientSession(); // aucune requête de cet onglet n'est rejouée sous l'ancien compte
    listener(data.reason === "logout" ? "logout" : "expired");
  };
  return () => channel.close();
}
