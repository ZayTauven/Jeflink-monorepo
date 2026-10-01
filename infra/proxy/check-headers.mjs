// Garde-fou CI (spec 001, infra 4, S9) : chaque en-tête X-Jeflink-* utilisé par l'API doit être
// retiré par le bord public. Sinon, un client pourrait l'envoyer jusqu'à Django.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const template = readFileSync("infra/proxy/templates/jeflink-api-locations.inc.template", "utf8");
const stripped = new Set(
  [...template.matchAll(/proxy_set_header\s+(X-Jeflink-[\w-]+)\s+""/g)].map((m) =>
    m[1].toLowerCase(),
  ),
);

const used = new Set();
function walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      if (!["tests", "migrations", "__pycache__"].includes(name)) walk(path);
    } else if (name.endsWith(".py")) {
      for (const m of readFileSync(path, "utf8").matchAll(/["'](X-Jeflink-[\w-]+)["']/gi)) {
        used.add(m[1].toLowerCase());
      }
    }
  }
}
walk("apps/api/jeflink");

const missing = [...used].filter((header) => !stripped.has(header));
if (missing.length) {
  console.error(`En-têtes X-Jeflink-* non retirés par le proxy : ${missing.join(", ")}`);
  process.exit(1);
}
console.log(`Proxy : ${used.size} en-tête(s) X-Jeflink-* retirés de l'extérieur.`);
