// Tests de la frise, de l'état de la mission et de l'actualisation (spec 004, web 1).
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { REFRESH_INTERVAL_MS, createAutoRefresh } from "./auto-refresh.ts";
import { currentStepIndex, isCodeStage, isMission, isMissionLive, missionSteps } from "./steps.ts";

const empty = {
  en_route_at: null,
  on_site_at: null,
  started_at: null,
  completed_at: null,
  closed_at: null,
};

describe("frise des étapes", () => {
  it("scheduled : première étape en cours, les autres à venir", () => {
    const steps = missionSteps({ status: "scheduled", ...empty });
    assert.deepEqual(
      steps?.map((s) => s.state),
      ["current", "upcoming", "upcoming", "upcoming", "upcoming", "upcoming"],
    );
  });
  it("in_progress : trois étapes faites avec leur heure, une en cours", () => {
    const steps = missionSteps({
      status: "in_progress",
      ...empty,
      en_route_at: "2026-10-04T08:00:00Z",
      on_site_at: "2026-10-04T08:30:00Z",
      started_at: "2026-10-04T08:40:00Z",
    });
    assert.deepEqual(
      steps?.map((s) => s.state),
      ["done", "done", "done", "current", "upcoming", "upcoming"],
    );
    assert.equal(steps?.[2]?.at, "2026-10-04T08:30:00Z");
    assert.equal(steps?.[4]?.at, null);
  });
  it("closed : tout est fait ; disputed reste à « terminé »", () => {
    const closed = missionSteps({ status: "closed", ...empty, closed_at: "2026-10-06T10:00:00Z" });
    assert.ok(closed?.every((s) => s.state === "done"));
    assert.equal(currentStepIndex("disputed"), 4);
  });
  it("hors déroulé (accepted, cancelled, inconnu) : pas de frise", () => {
    for (const status of ["accepted", "cancelled", "zzz"]) {
      assert.equal(missionSteps({ status, ...empty } as never), null);
      assert.equal(isMission(status), false);
    }
  });
  it("la mission est « en cours » de scheduled à in_progress seulement", () => {
    for (const s of ["scheduled", "en_route", "on_site", "in_progress"]) {
      assert.ok(isMissionLive(s));
      assert.ok(isCodeStage(s));
    }
    for (const s of ["completed", "disputed", "closed", "cancelled", "accepted"]) {
      assert.equal(isMissionLive(s), false);
      assert.equal(isCodeStage(s), false);
    }
  });
});

describe("actualisation automatique", () => {
  function harness(opts: { visible?: boolean; online?: boolean } = {}) {
    const state = { visible: opts.visible ?? true, online: opts.online ?? true, time: 0, ticks: 0 };
    let run: (() => void) | null = null;
    const refresh = createAutoRefresh({
      tick: () => (state.ticks += 1),
      isVisible: () => state.visible,
      isOnline: () => state.online,
      now: () => state.time,
      setTimer: (fn) => {
        run = fn;
        return 1;
      },
      clearTimer: () => {
        run = null;
      },
    });
    const advance = (ms: number) => {
      state.time += ms;
      (run as (() => void) | null)?.();
    };
    return { state, refresh, advance, armed: () => run !== null };
  }

  it("actualise toutes les 60 s, onglet visible et mission en cours", () => {
    const h = harness();
    h.refresh.sync(true);
    assert.equal(REFRESH_INTERVAL_MS, 60_000);
    h.advance(60_000);
    h.advance(60_000);
    assert.equal(h.state.ticks, 2);
  });
  it("aucun minuteur quand la mission n'est plus en cours", () => {
    const h = harness();
    h.refresh.sync(false);
    assert.equal(h.armed(), false);
  });
  it("onglet caché : minuteur coupé, aucune actualisation", () => {
    const h = harness({ visible: false });
    h.refresh.sync(true);
    assert.equal(h.armed(), false);
    assert.equal(h.state.ticks, 0);
  });
  it("onglet qui se cache : le minuteur s'arrête", () => {
    const h = harness();
    h.refresh.sync(true);
    h.state.visible = false;
    h.refresh.sync(true);
    assert.equal(h.armed(), false);
  });
  it("retour sur l'onglet après plus d'une minute : actualise tout de suite", () => {
    const h = harness();
    h.refresh.sync(true);
    h.state.visible = false;
    h.refresh.sync(true);
    h.state.time += 5 * 60_000;
    h.state.visible = true;
    h.refresh.sync(true);
    assert.equal(h.state.ticks, 1);
  });
  it("retour rapide : pas d'actualisation en double", () => {
    const h = harness();
    h.refresh.sync(true);
    h.state.visible = false;
    h.refresh.sync(true);
    h.state.time += 10_000;
    h.state.visible = true;
    h.refresh.sync(true);
    assert.equal(h.state.ticks, 0);
  });
  it("hors ligne : on saute le tour", () => {
    const h = harness({ online: false });
    h.refresh.sync(true);
    h.advance(60_000);
    assert.equal(h.state.ticks, 0);
  });
  it("sync répété n'arme qu'un seul minuteur", () => {
    const h = harness();
    h.refresh.sync(true);
    h.refresh.sync(true);
    h.advance(60_000);
    assert.equal(h.state.ticks, 1);
  });
});
