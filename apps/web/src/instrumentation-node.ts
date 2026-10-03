// Vérification de démarrage, runtime Node seulement (importé par instrumentation.ts).
import { bff } from "./lib/bff.ts";
import { readSiteConfig } from "./lib/site-config.ts";

try {
  bff();
  readSiteConfig(process.env);
} catch (error) {
  // Next garderait un processus vivant qui ne sert rien : on sort, l'orchestrateur le voit.
  // Le message ne nomme que la variable, jamais une valeur.
  console.error(error instanceof Error ? error.message : "BFF web : configuration invalide.");
  process.exit(1);
}
