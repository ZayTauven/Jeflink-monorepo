// Test de build sans secret (spec 001, web 1).
//
// 1. `next build` passe sans AUCUNE variable du BFF : rien n'est lu ni exigé au build.
// 2. `next build` avec des valeurs témoins : aucune n'apparaît dans `.next/` (bundles navigateur,
//    pages prérendues, fichiers serveur). Les variables du BFF sont lues à l'exécution seulement.
import { spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const BFF_VARS = [
  "JEFLINK_API_URL",
  "BFF_SHARED_SECRET",
  "BFF_ALLOWED_ORIGINS",
  "BFF_CLIENT_IP_HEADER",
  "BFF_COOKIE_DOMAIN",
];

function build(extra) {
  const env = { ...process.env, NEXT_TELEMETRY_DISABLED: "1" };
  for (const name of BFF_VARS) delete env[name];
  Object.assign(env, extra);
  const result = spawnSync("pnpm", ["exec", "next", "build"], {
    cwd: root,
    env,
    stdio: "inherit",
    shell: process.platform === "win32",
  });
  if (result.status !== 0) {
    console.error("Échec : next build a échoué.");
    process.exit(1);
  }
}

function* files(dir) {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      if (path === join(root, ".next", "cache")) continue;
      yield* files(path);
    } else {
      yield path;
    }
  }
}

console.log("\n[1/2] next build sans aucune variable du BFF\n");
build({});

const tag = randomBytes(12).toString("hex");
const canaries = {
  JEFLINK_API_URL: `https://canary-api-${tag}.invalid`,
  BFF_SHARED_SECRET: `canary-secret-${tag}-${randomBytes(16).toString("hex")}`,
  BFF_ALLOWED_ORIGINS: `https://canary-origin-${tag}.invalid`,
  BFF_CLIENT_IP_HEADER: `x-canary-${tag}`,
  BFF_COOKIE_DOMAIN: `canary-${tag}.invalid`,
};
console.log("\n[2/2] next build avec des valeurs témoins\n");
build(canaries);

const leaks = [];
for (const path of files(join(root, ".next"))) {
  const content = readFileSync(path, "latin1");
  if (!content.includes(tag)) continue;
  const names = Object.entries(canaries)
    .filter(([, value]) => content.includes(value))
    .map(([name]) => name);
  leaks.push(`${names.join(", ") || "valeur témoin partielle"} → ${path}`);
}
if (leaks.length) {
  console.error("Échec : une variable du BFF a été figée dans le build :");
  for (const leak of leaks) console.error(`  ${leak}`);
  process.exit(1);
}
console.log("\nOK : build sans secret, aucune variable du BFF dans .next/.");
