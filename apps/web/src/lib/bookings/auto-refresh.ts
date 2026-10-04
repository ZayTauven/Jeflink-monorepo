// Actualisation automatique du suivi (spec 004, web 1) : toutes les 60 s, seulement quand l'onglet
// est visible et la mission en cours. Hors ligne, on saute le tour (le bouton « Actualiser » dit
// l'état du réseau). Logique pure : minuteurs et visibilité sont injectés, donc testables sans
// navigateur.

export const REFRESH_INTERVAL_MS = 60_000;

export type AutoRefreshDeps = {
  tick: () => void;
  isVisible: () => boolean;
  isOnline: () => boolean;
  now: () => number;
  setTimer: (run: () => void, ms: number) => unknown;
  clearTimer: (handle: unknown) => void;
  intervalMs?: number;
};

export type AutoRefresh = {
  /** À appeler au montage et à chaque changement (visibilité, statut) : arme ou coupe le minuteur. */
  sync: (active: boolean) => void;
  stop: () => void;
};

export function createAutoRefresh(deps: AutoRefreshDeps): AutoRefresh {
  const interval = deps.intervalMs ?? REFRESH_INTERVAL_MS;
  let handle: unknown = null;
  let last = deps.now();

  function fire(): void {
    last = deps.now();
    if (deps.isVisible() && deps.isOnline()) deps.tick();
  }

  function stop(): void {
    if (handle !== null) {
      deps.clearTimer(handle);
      handle = null;
    }
  }

  function sync(active: boolean): void {
    if (!active || !deps.isVisible()) {
      stop();
      return;
    }
    if (handle !== null) return;
    // L'onglet redevient visible après plus d'une minute : la page est périmée, on actualise tout de suite.
    if (deps.now() - last >= interval) fire();
    handle = deps.setTimer(fire, interval);
  }

  return { sync, stop };
}
