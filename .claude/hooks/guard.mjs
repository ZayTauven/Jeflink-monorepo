// Bloque l'écriture dans les fichiers qui ne doivent jamais être édités à la main.
// Code de sortie 2 = action refusée, le message (stderr) est renvoyé à Claude.
import { readTarget } from "./_input.mjs";

const target = await readTarget();
if (!target) process.exit(0);
const { rel, name } = target;

function refuse(message) {
  process.stderr.write(`Refusé : ${message}\n`);
  process.exit(2);
}

// Les .env* sont lisibles et modifiables par Claude (décision Zay, 2026-09-30) ; leur contenu
// n'est jamais exposé ni recopié ailleurs : voir « Secrets » dans CLAUDE.md.
if (rel.startsWith("apps/web/public/crafto/")) {
  refuse(
    "copie du template Crafto, régénérée par scripts/sync-crafto.mjs. Mets tes ajouts dans apps/web/public/jeflink.css.",
  );
}
if (rel.startsWith("references/")) {
  refuse(
    "references/ est du matériel de référence en lecture seule (templates, originaux). Reconstruis dans apps/ ou packages/.",
  );
}
process.exit(0);
