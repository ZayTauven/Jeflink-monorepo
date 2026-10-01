// Tests de la configuration du BFF web (spec 001, web 1) : variables serveur et IP cliente.
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { BffConfigError, WEB_REFRESH_MAX_AGE_SECONDS, readBffConfig } from "./bff-config.ts";
import { LOGIN_PATH } from "./routes.ts";

const SECRET = "s".repeat(40);
const production = {
  NODE_ENV: "production",
  JEFLINK_API_URL: "https://api",
  BFF_SHARED_SECRET: SECRET,
  BFF_ALLOWED_ORIGINS: "https://jeflink.sn, https://www.jeflink.sn",
  BFF_CLIENT_IP_HEADER: "X-Real-IP",
  BFF_COOKIE_DOMAIN: "jeflink.sn",
};

const request = (headers: Record<string, string>) => new Headers(headers);

describe("readBffConfig", () => {
  it("production complète : app web imposée, origines exactes, IP lue dans l'en-tête choisi", () => {
    const config = readBffConfig(production);
    assert.equal(config.app, "web");
    assert.equal(config.apiUrl, "https://api");
    assert.deepEqual(config.allowedOrigins, ["https://jeflink.sn", "https://www.jeflink.sn"]);
    assert.equal(config.refreshMaxAgeSeconds, WEB_REFRESH_MAX_AGE_SECONDS);
    assert.equal(config.loginPath, LOGIN_PATH);
    assert.equal(config.clientIp(request({ "x-real-ip": "41.82.1.2" })), "41.82.1.2");
    assert.equal(config.clientIp(request({ "x-forwarded-for": "41.82.1.2" })), null);
  });

  for (const name of [
    "BFF_SHARED_SECRET",
    "JEFLINK_API_URL",
    "BFF_ALLOWED_ORIGINS",
    "BFF_COOKIE_DOMAIN",
  ]) {
    it(`production : ${name} absente → refus, sans valeur dans le message`, () => {
      assert.throws(
        () => readBffConfig({ ...production, [name]: " " }),
        (error: unknown) => {
          assert.ok(error instanceof BffConfigError);
          assert.match(error.message, new RegExp(name));
          assert.doesNotMatch(error.message, new RegExp(SECRET));
          return true;
        },
      );
    });
  }

  it("production : IP cliente obligatoire", () => {
    assert.throws(
      () => readBffConfig({ ...production, BFF_CLIENT_IP_HEADER: undefined }),
      /BFF_CLIENT_IP_HEADER/,
    );
  });

  for (const header of ["X-Forwarded-For", "forwarded", "x-real-ip, x-forwarded-for"]) {
    it(`IP cliente : « ${header} » refusé comme source`, () => {
      assert.throws(
        () => readBffConfig({ ...production, BFF_CLIENT_IP_HEADER: header }),
        /BFF_CLIENT_IP_HEADER/,
      );
    });
  }

  it("production : API et origines en https seulement", () => {
    assert.throws(
      () => readBffConfig({ ...production, JEFLINK_API_URL: "http://api" }),
      /JEFLINK_API_URL/,
    );
    assert.throws(
      () => readBffConfig({ ...production, BFF_ALLOWED_ORIGINS: "http://jeflink.sn" }),
      /BFF_ALLOWED_ORIGINS/,
    );
  });

  it("domaine des cookies : nom de domaine seulement, facultatif hors production", () => {
    assert.equal(
      readBffConfig({ NODE_ENV: "development", BFF_SHARED_SECRET: SECRET }).cookieDomain,
      undefined,
    );
    assert.equal(
      readBffConfig({ ...production, BFF_COOKIE_DOMAIN: "Jeflink.sn" }).cookieDomain,
      "jeflink.sn",
    );
    for (const domain of [".jeflink.sn", "localhost", "jeflink.sn; Secure"]) {
      assert.throws(
        () => readBffConfig({ ...production, BFF_COOKIE_DOMAIN: domain }),
        /BFF_COOKIE_DOMAIN/,
      );
    }
  });

  for (const nodeEnv of [undefined, "", "test", "staging", "preprod", "Development"]) {
    it(`NODE_ENV=${JSON.stringify(nodeEnv)} : règles de production, aucun repli de dev`, () => {
      assert.throws(
        () => readBffConfig({ NODE_ENV: nodeEnv, BFF_SHARED_SECRET: SECRET }),
        /JEFLINK_API_URL/,
      );
      assert.throws(
        () => readBffConfig({ ...production, NODE_ENV: nodeEnv, BFF_CLIENT_IP_HEADER: undefined }),
        /BFF_CLIENT_IP_HEADER/,
      );
    });
  }

  for (const apiUrl of [
    "https://jeflink.sn",
    "https://www.jeflink.sn",
    "https://api.jeflink.sn",
    "https://JEFLINK.SN:8443",
    "https://",
  ]) {
    it(`production : API « ${apiUrl} » refusée (hôte public)`, () => {
      assert.throws(
        () => readBffConfig({ ...production, JEFLINK_API_URL: apiUrl }),
        /JEFLINK_API_URL/,
      );
    });
  }

  it("local : seul le secret est exigé, valeurs de dev par défaut", () => {
    assert.throws(() => readBffConfig({ NODE_ENV: "development" }), /BFF_SHARED_SECRET/);
    const config = readBffConfig({ NODE_ENV: "development", BFF_SHARED_SECRET: SECRET });
    assert.equal(config.apiUrl, "http://localhost:8000");
    assert.deepEqual(config.allowedOrigins, ["http://localhost:3000"]);
    assert.equal(config.clientIp(request({ "x-real-ip": "41.82.1.2" })), "127.0.0.1");
  });
});
