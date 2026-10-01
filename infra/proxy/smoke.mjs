// Contrôles du bord public (spec 001, infra 4) sur le vrai nginx et la vraie API en réglages de
// production. Lancé par run-smoke.mjs (qui démarre et retire les services).
import { execFileSync } from "node:child_process";
import http from "node:http";

const HOST = "edge.localhost";
const COMPOSE = [
  "compose",
  "-f",
  "infra/docker-compose.yml",
  "-f",
  "infra/docker-compose.edge.yml",
];

function request(port, path, headers = {}) {
  return new Promise((resolve) => {
    const req = http.request(
      { host: "127.0.0.1", port, path, method: "GET", headers: { Host: HOST, ...headers } },
      (res) => {
        let data = "";
        res.on("data", (chunk) => (data += chunk));
        res.on("end", () => resolve({ status: res.statusCode, body: data }));
      },
    );
    req.on("error", (error) => resolve({ error: error.code || String(error) }));
    req.end();
  });
}

const SPOOFED = {
  "X-Forwarded-For": "203.0.113.7",
  "X-Forwarded-Proto": "http",
  "X-Forwarded-Host": "api",
  "X-Forwarded-Port": "443",
  Forwarded: "for=203.0.113.7;host=api",
  "X-Real-IP": "203.0.113.7",
  "X-Jeflink-Bff": "forge",
  "X-Jeflink-Client-Ip": "203.0.113.7",
  "X-Jeflink-App": "console",
};

export async function runChecks() {
  let failures = 0;
  const check = (label, ok) => {
    console.log(`${ok ? "ok   " : "ÉCHEC"} ${label}`);
    if (!ok) failures += 1;
  };

  // 1. Ce que l'API recevrait : amont écho derrière le même nginx.
  const echo = await request(8089, "/api/x/", SPOOFED);
  const seen = echo.body ? JSON.parse(echo.body) : {};
  check("écho joignable", echo.status === 200);
  check("aucun X-Jeflink-* transmis", !Object.keys(seen).some((h) => h.startsWith("x-jeflink-")));
  for (const name of ["forwarded", "x-forwarded-host", "x-forwarded-port", "x-real-ip"]) {
    check(`${name} retiré`, !(name in seen));
  }
  const xff = seen["x-forwarded-for"] ?? "";
  check(
    "X-Forwarded-For : une seule adresse, jamais l'usurpée",
    /^[0-9a-f.:]+$/i.test(xff) && !xff.includes("203.0.113.7"),
  );
  check("X-Forwarded-Proto imposé à https", seen["x-forwarded-proto"] === "https");
  check("Host = hôte public", seen.host === HOST);

  // 2. API réelle en réglages de production.
  const health = await request(8088, "/api/health/", SPOOFED);
  check("API servie en réglages de production (200, sans redirection)", health.status === 200);
  const me = await request(8088, "/api/me/");
  check("Bearer exigé (401)", me.status === 401);
  const logs = execFileSync("docker", [...COMPOSE, "logs", "--tail", "50", "api-asgi"], {
    encoding: "utf8",
  });
  check(
    "IP vue par l'API = IP réelle du client (reprise du seul proxy)",
    logs.includes(`${xff}:0 - "GET /api/health/`),
  );
  check("IP usurpée jamais vue par l'API", !logs.includes("203.0.113.7"));

  // 3. Hôtes et chemins.
  for (const host of ["api", "localhost", "inconnu.example"]) {
    const closed = await request(8088, "/api/health/", { Host: host });
    check(`hôte « ${host} » : connexion fermée sans réponse`, Boolean(closed.error));
  }
  for (const path of [
    "/admin/",
    "/admin/login/",
    "/api/schema/",
    "/api/docs/",
    "/api/internal/x",
    "/api/../admin/",
    "/api/%2e%2e/admin/",
    "/",
  ]) {
    const res = await request(8088, path);
    check(`${path} : jamais servi (404)`, res.status === 404);
  }
  return failures;
}
