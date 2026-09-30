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

if (name.startsWith(".env") && name !== ".env.example") {
  refuse("les fichiers .env ne sont pas édités par Claude. Modifie .env.example et signale-le.");
}
if (rel.startsWith("packages/api-client/src/generated/")) {
  refuse("client généré. Modifie l'API Django puis lance 'make openapi'.");
}
if (rel.startsWith("references/") || rel.startsWith("Crafto - The Multipurpose HTML5 Template/")) {
  refuse(
    "references/ est du matériel de référence en lecture seule (templates, originaux). Reconstruis dans apps/ ou packages/.",
  );
}
process.exit(0);
