// Pré-commit (spec 001, S21) : gitleaks sur les changements indexés, avant qu'un secret
// n'entre dans l'historique. Binaire local si présent, sinon image Docker officielle, sinon refus
// avec la marche à suivre. Contourner (git commit --no-verify) est réservé à un cas expliqué.
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";

const IMAGE =
  "ghcr.io/gitleaks/gitleaks:v8.28.0@sha256:cdbb7c955abce02001a9f6c9f602fb195b7fadc1e812065883f695d1eeaba854";
// [[allowlists]] exige gitleaks 8.25 ou plus.
const MIN_VERSION = [8, 25, 0];
const root = spawnSync("git", ["rev-parse", "--show-toplevel"], { encoding: "utf8" }).stdout.trim();
const args = ["git", "--pre-commit", "--staged", "--redact", "--no-banner", "--config"];

function run(command, commandArgs, options = {}) {
  return spawnSync(command, commandArgs, { stdio: "inherit", ...options });
}

function available(command, probe) {
  const result = spawnSync(command, probe, { stdio: "ignore" });
  return !result.error && result.status === 0;
}

function localGitleaksRecent() {
  const result = spawnSync("gitleaks", ["version"], { encoding: "utf8" });
  if (result.error || result.status !== 0) return false;
  const found = (result.stdout.match(/(\d+)\.(\d+)\.(\d+)/) ?? []).slice(1).map(Number);
  if (found.length !== 3) return false;
  for (let i = 0; i < 3; i += 1) {
    if (found[i] !== MIN_VERSION[i]) return found[i] > MIN_VERSION[i];
  }
  return true;
}

let result;
if (localGitleaksRecent()) {
  result = run("gitleaks", [...args, resolve(root, ".gitleaks.toml"), root]);
} else if (available("docker", ["info"])) {
  result = run(
    "docker",
    ["run", "--rm", "-v", `${root}:/repo`, IMAGE, ...args, "/repo/.gitleaks.toml", "/repo"],
    { env: { ...process.env, MSYS_NO_PATHCONV: "1" } },
  );
} else {
  console.error(
    "\n[gitleaks] Ni gitleaks ni Docker disponible : commit refusé.\n" +
      "Installez gitleaks (Windows : `scoop install gitleaks`) ou démarrez Docker Desktop.\n" +
      "Voir « Prérequis » dans README.md.\n",
  );
  process.exit(1);
}

if (result.status === 1) {
  console.error(
    "\n[gitleaks] Secret probable dans les changements indexés : commit refusé.\n" +
      "Retirez-le (et changez-le s'il est réel). Valeur factice de test : voir .gitleaks.toml.\n",
  );
} else if (result.status !== 0) {
  console.error(
    `\n[gitleaks] Échec de l'analyse (code ${result.status ?? "inconnu"}) : commit refusé.\n` +
      "Vérifiez Docker ou mettez gitleaks à jour (8.25 ou plus).\n",
  );
}
process.exit(result.status ?? 1);
