// Tests des redirections serveur (spec 001, web 1 ; revue web 1, I-3 et m-5).
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { isLoginPath, sessionRedirect, unauthorizedRedirect } from "./session-redirects.ts";

const refreshPath = (next: string) => `/api/auth/token/refresh/?next=${encodeURIComponent(next)}`;
const expired = { needsRefresh: true, refreshPath };
const present = { needsRefresh: false, refreshPath };

class ApiError extends Error {
  readonly status: number;
  constructor(status: number) {
    super(`HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
  }
}

describe("sessionRedirect", () => {
  it("accès expiré mais refresh possible : rebond de refresh vers la page courante", () => {
    assert.equal(sessionRedirect(expired, "/compte?onglet=2"), refreshPath("/compte?onglet=2"));
  });

  it("accès présent ou aucune session : pas de redirection", () => {
    assert.equal(sessionRedirect(present, "/compte"), null);
  });
});

describe("unauthorizedRedirect", () => {
  it("401 avec un accès présent (session révoquée) : connexion, jamais le refresh", () => {
    assert.equal(
      unauthorizedRedirect(new ApiError(401), present, "/compte"),
      "/connexion?next=%2Fcompte",
    );
  });

  it("401 avec un accès expiré : refresh d'abord (pas d'OTP ni de SMS pour rien)", () => {
    assert.equal(
      unauthorizedRedirect(new ApiError(401), expired, "/compte"),
      refreshPath("/compte"),
    );
  });

  for (const path of ["/connexion", "/connexion?next=%2Fcompte", "/connexion/code"]) {
    it(`sur ${path} : erreur relancée, aucune boucle de redirection`, () => {
      assert.equal(unauthorizedRedirect(new ApiError(401), present, path), null);
      assert.equal(unauthorizedRedirect(new ApiError(401), expired, path), null);
    });
  }

  it("autre erreur qu'un 401 : relancée", () => {
    assert.equal(unauthorizedRedirect(new ApiError(403), present, "/compte"), null);
    assert.equal(unauthorizedRedirect(new ApiError(500), present, "/compte"), null);
    assert.equal(unauthorizedRedirect(new Error("réseau"), present, "/compte"), null);
    assert.equal(unauthorizedRedirect({ status: 401 }, present, "/compte"), null);
  });
});

describe("isLoginPath", () => {
  it("reconnaît la connexion, pas les chemins voisins", () => {
    assert.equal(isLoginPath("/connexion"), true);
    assert.equal(isLoginPath("/connexion?next=%2F"), true);
    assert.equal(isLoginPath("/connexion/code"), true);
    assert.equal(isLoginPath("/connexion-pro"), false);
    assert.equal(isLoginPath("/"), false);
  });
});
