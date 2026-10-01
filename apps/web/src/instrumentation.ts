// Au démarrage du serveur : configuration du BFF validée tout de suite (une variable manquante
// arrête le serveur au lieu de faire échouer la première requête). Rien au build : `next build`
// passe sans secret (spec 001, web 1).
export async function register(): Promise<void> {
  if (process.env.NEXT_PHASE === "phase-production-build") return;
  if (process.env.NEXT_RUNTIME === "nodejs") await import("./instrumentation-node.ts");
}
