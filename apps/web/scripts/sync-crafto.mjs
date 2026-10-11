// Copie les fichiers du template Crafto (CSS, polices d'icônes, JS, images de la démo
// « Marketing strategy ») depuis references/crafto vers public/crafto.
//
// Crafto est sous licence Envato et le dépôt est public : ces fichiers ne sont jamais versionnés
// (public/crafto est dans .gitignore). Chaque poste de dev les recopie depuis sa copie locale du
// template. Dossier source modifiable avec CRAFTO_DIR.
import { copyFileSync, existsSync, mkdirSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const src = resolve(process.env.CRAFTO_DIR ?? join(webDir, "../../references/crafto"));
const dest = join(webDir, "public/crafto");

if (!existsSync(join(src, "css/style.min.css"))) {
  console.error(
    `\n[crafto] Template introuvable dans ${src}.\n` +
      "Placez le dossier Crafto dans references/crafto (ou définissez CRAFTO_DIR), puis relancez.\n",
  );
  process.exit(1);
}

const files = [
  "css/vendors.min.css",
  "css/icon.min.css",
  "css/style.min.css",
  "css/responsive.min.css",
  "demos/marketing-strategy/marketing-strategy.css",
  "js/jquery.js",
  "js/vendors.min.js",
  "js/main.js",
  ...readdirSync(join(src, "fonts")).map((f) => `fonts/${f}`),
  ...readdirSync(join(src, "images"))
    .filter(
      (f) =>
        f.startsWith("demo-marketing-strategy") ||
        /^demo-branding-studio-client-0\d\.svg$/.test(f) ||
        f.startsWith("apple-touch-icon") ||
        [
          "favicon.png",
          "contact-form-arrow-white.png",
          "contact-form-down-arrow.jpg",
          "mfg-close.png",
        ].includes(f),
    )
    .map((f) => `images/${f}`),
];

let copied = 0;
for (const rel of files) {
  const from = join(src, rel);
  const to = join(dest, rel);
  const s = statSync(from);
  if (existsSync(to)) {
    const d = statSync(to);
    if (d.size === s.size && d.mtimeMs >= s.mtimeMs) continue;
  }
  mkdirSync(dirname(to), { recursive: true });
  copyFileSync(from, to);
  copied += 1;
}
console.log(`[crafto] ${files.length} fichiers prêts dans public/crafto (${copied} copiés).`);
