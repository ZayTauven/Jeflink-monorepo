// Test de fumée du bord public (spec 001, infra 4), en local et en CI :
//   node infra/proxy/run-smoke.mjs
// Génère des secrets aléatoires (jamais écrits sur disque), démarre nginx et l'API en réglages de
// production, lance les contrôles, puis retire les services du test.
import { spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import http from "node:http";

import { runChecks } from "./smoke.mjs";

const COMPOSE = [
  "compose",
  "-f",
  "infra/docker-compose.yml",
  "-f",
  "infra/docker-compose.edge.yml",
];
const SERVICES = ["redis-smoke", "api-asgi", "echo", "edge", "edge-echo"];
const secret = () => randomBytes(36).toString("base64url");

// Dans l'environnement du processus : tous les appels à docker compose en héritent.
const env = Object.assign(process.env, {
  SMOKE_SECRET_KEY: secret(),
  SMOKE_JWT_KEY: secret(),
  SMOKE_OTP_KEY: secret(),
  SMOKE_BFF_SECRET: secret(),
  SMOKE_PII_KEY: secret(),
  SMOKE_REDIS_PASSWORD: secret(),
  SMOKE_MFA_KEY: randomBytes(32).toString("base64url") + "=",
});

function docker(args, options = {}) {
  return spawnSync("docker", [...COMPOSE, ...args], { env, stdio: "inherit", ...options });
}

function healthy() {
  return new Promise((resolve) => {
    const req = http.request(
      { host: "127.0.0.1", port: 8088, path: "/api/health/", headers: { Host: "edge.localhost" } },
      (res) => {
        res.resume();
        resolve(res.statusCode === 200);
      },
    );
    req.on("error", () => resolve(false));
    req.end();
  });
}

let failures = 1;
try {
  if (docker(["up", "-d", "--build", ...SERVICES]).status !== 0) throw new Error("démarrage");
  let ready = false;
  for (let i = 0; i < 60 && !ready; i += 1) {
    ready = await healthy();
    if (!ready) await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  if (!ready) {
    docker(["logs", "--tail", "40", "api-asgi"]);
    throw new Error("l'API ne répond pas (voir les journaux ci-dessus)");
  }
  failures = await runChecks();
} catch (error) {
  console.error(`Test de fumée interrompu : ${error.message}`);
} finally {
  docker(["rm", "-sf", ...SERVICES], { stdio: "ignore" });
}
console.log(failures ? `\n${failures} échec(s)` : "\nBord public conforme.");
process.exit(failures ? 1 : 0);
