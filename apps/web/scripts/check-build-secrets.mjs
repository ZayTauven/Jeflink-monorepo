// Test de build sans secret (spec 001, web 1 ; revue web 1, m-6).
//
// 1. `next build` passe sans AUCUNE variable serveur : rien n'est lu ni exigé au build.
// 2. `next build` avec des valeurs témoins : aucune n'apparaît dans `.next/`, cache compris
//    (une image copie souvent tout `.next`). Les variables sont lues à l'exécution seulement.
//
// La liste des variables vient de `.env.example` : une variable ajoutée y est testée d'office.
// Le test refuse de tourner si un `.env*` local existe : Next le chargerait et l'étape 1 ne
// prouverait plus rien.
import { spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { readdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));

function fail(message) {
  console.error(`Échec : ${message}`);
  process.exit(1);
}

const localEnvFiles = readdirSync(root).filter(
  (name) => name.startsWith(".env") && name !== ".env.example",
);
if (localEnvFiles.length) {
  fail(
    `fichier d'environnement local présent (${localEnvFiles.join(", ")}). ` +
      "Next le chargerait au build : lancer le test sur une copie propre (en CI).",
  );
}

const names = readFileSync(join(root, ".env.example"), "utf8")
  .split(/\r?\n/)
  .map((line) => /^([A-Z][A-Z0-9_]*)=/.exec(line.trim())?.[1])
  .filter(Boolean);
if (!names.length) fail(".env.example ne déclare aucune variable.");
const published = names.filter((name) => name.startsWith("NEXT_PUBLIC_"));
if (published.length) {
  fail(`variable publique dans .env.example (${published.join(", ")}) : jamais de NEXT_PUBLIC_.`);
}

function build(extra) {
  rmSync(join(root, ".next"), { recursive: true, force: true });
  const env = { ...process.env, NEXT_TELEMETRY_DISABLED: "1" };
  for (const name of names) delete env[name];
  Object.assign(env, extra);
  const result = spawnSync("pnpm", ["exec", "next", "build"], {
    cwd: root,
    env,
    stdio: "inherit",
    shell: process.platform === "win32",
  });
  if (result.status !== 0) fail("next build a échoué.");
}

function* files(dir) {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) yield* files(path);
    else yield path;
  }
}

console.log(`\n[1/2] next build sans aucune variable serveur (${names.join(", ")})\n`);
build({});

const tag = randomBytes(12).toString("hex");
// Valeurs témoins : jamais affichées en clair dans le rapport, seulement le nom de la variable.
const canaries = Object.fromEntries(
  names.map((name, index) => [name, `canary-${tag}-${index}-${randomBytes(8).toString("hex")}`]),
);
console.log("\n[2/2] next build avec des valeurs témoins\n");
build(canaries);

const leaks = [];
for (const path of files(join(root, ".next"))) {
  const content = readFileSync(path, "latin1");
  if (!content.includes(tag)) continue;
  const found = Object.entries(canaries)
    .filter(([, value]) => content.includes(value))
    .map(([name]) => name);
  leaks.push(`${found.join(", ") || "valeur témoin partielle"} → ${path}`);
}
if (leaks.length) {
  console.error("Échec : une variable serveur a été figée dans le build :");
  for (const leak of leaks) console.error(`  ${leak}`);
  process.exit(1);
}
console.log("\nOK : build sans secret, aucune variable serveur dans .next/ (cache compris).");
