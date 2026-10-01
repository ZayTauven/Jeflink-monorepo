// Au démarrage du serveur : configuration du BFF validée tout de suite (une variable manquante
// arrête le serveur au lieu de faire échouer la première requête). Rien au build : `next build`
// passe sans secret (spec 001, web 1).
export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  if (process.env.NEXT_PHASE === "phase-production-build") return;
  const { bff } = await import("./lib/bff");
  try {
    bff();
  } catch (error) {
    // Next garderait un processus vivant qui ne sert rien : on sort, l'orchestrateur le voit.
    // Le message ne nomme que la variable, jamais une valeur.
    console.error(error instanceof Error ? error.message : "BFF web : configuration invalide.");
    process.exit(1);
  }
}
