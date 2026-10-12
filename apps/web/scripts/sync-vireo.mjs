// Copie les fichiers du template vireo utilisés par la console (feuilles de style et graphiques
// ApexCharts) depuis references/vireo vers src/vireo.
//
// vireo est sous licence Envato et le dépôt est public : ces fichiers ne sont jamais versionnés
// (src/vireo est dans .gitignore). Chaque poste de dev les recopie depuis sa copie locale du
// template. L'habillage Jeflink (Crafto) vit dans src/console/console.css, versionné.
// Dossier source modifiable avec VIREO_DIR.
import { copyFileSync, existsSync, mkdirSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const src = resolve(process.env.VIREO_DIR ?? join(webDir, "../../references/vireo"));
const dest = join(webDir, "src/vireo");

if (!existsSync(join(src, "src/styles/app.css"))) {
  console.error(
    `\n[vireo] Template introuvable dans ${src}.\n` +
      "Placez le dossier vireo dans references/vireo (ou définissez VIREO_DIR), puis relancez.\n",
  );
  process.exit(1);
}

/** Tous les fichiers d'un dossier, récursivement, en chemins relatifs à `root`. */
function walk(dir, root = dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path, root) : [relative(root, path)];
  });
}

const groups = [
  ["src/styles", "styles"],
  ["src/components/charts", "charts"],
];

let total = 0;
let copied = 0;
for (const [from, to] of groups) {
  for (const rel of walk(join(src, from))) {
    const a = join(src, from, rel);
    const b = join(dest, to, rel);
    total += 1;
    const s = statSync(a);
    if (existsSync(b)) {
      const d = statSync(b);
      if (d.size === s.size && d.mtimeMs >= s.mtimeMs) continue;
    }
    mkdirSync(dirname(b), { recursive: true });
    copyFileSync(a, b);
    copied += 1;
  }
}
console.log(`[vireo] ${total} fichiers prêts dans src/vireo (${copied} copiés).`);
