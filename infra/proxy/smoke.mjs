// Test de fumée du bord public (spec 001, infra 4). Prérequis :
//   docker compose -f infra/docker-compose.yml -f infra/docker-compose.edge.yml up -d edge api-asgi
// Vérifie sur le vrai nginx et le vrai uvicorn : hôte inconnu fermé, routes internes jamais
// servies, en-têtes X-Jeflink-* et X-Forwarded-For venus de l'extérieur sans effet.
import { execFileSync } from "node:child_process";
import http from "node:http";

const PORT = 8088;
const HOST = "edge.localhost";
let failures = 0;

function request(path, headers = {}) {
  return new Promise((resolve) => {
    const req = http.request(
      { host: "127.0.0.1", port: PORT, path, method: "GET", headers: { Host: HOST, ...headers } },
      (res) => {
        res.resume();
        res.on("end", () => resolve({ status: res.statusCode }));
      },
    );
    req.on("error", (error) => resolve({ error: error.code || String(error) }));
    req.end();
  });
}

function check(label, ok) {
  console.log(`${ok ? "ok  " : "ÉCHEC"} ${label}`);
  if (!ok) failures += 1;
}

const health = await request("/api/health/");
check("API publique servie (200)", health.status === 200);

for (const host of ["api", "inconnu.example"]) {
  const closed = await request("/api/health/", { Host: host });
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
  const res = await request(path);
  check(`${path} : jamais servi (404)`, res.status === 404);
}

// IP usurpée : nginx écrase X-Forwarded-For, uvicorn ne journalise jamais 203.0.113.7.
await request("/api/health/", {
  "X-Forwarded-For": "203.0.113.7",
  "X-Jeflink-Client-Ip": "203.0.113.7",
});
const logs = execFileSync(
  "docker",
  [
    "compose",
    "-f",
    "infra/docker-compose.yml",
    "-f",
    "infra/docker-compose.edge.yml",
    "logs",
    "--tail",
    "20",
    "api-asgi",
  ],
  { encoding: "utf8" },
);
check("X-Forwarded-For usurpé sans effet sur l'IP vue par l'API", !logs.includes("203.0.113.7"));
check(
  "IP cliente reprise du proxy (pas l'IP de nginx)",
  !/172\.30\.0\.10:\d+ - "GET \/api\/health/.test(logs),
);

console.log(failures ? `\n${failures} échec(s)` : "\nBord public conforme.");
process.exit(failures ? 1 : 0);
