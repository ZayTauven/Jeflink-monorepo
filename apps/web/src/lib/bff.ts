// BFF de l'app web (spec 001, web 1 ; ADR 0007). `server-only` : importer ce module depuis un
// Client Component casse le build.
//
// Côté serveur :
// - page : `serverApiWithSession()` (ou `serverApi()` si la session est facultative), puis
//   `options` passé à chaque appel généré ; jamais à un Client Component ni dans un
//   `HydrationBoundary`. Une erreur d'appel passe par `rethrowApiError()` ;
// - Server Action : `serverApi()` ; si `needsRefresh`, renvoyer `{ needsRefresh: true }` (le client
//   rafraîchit puis rejoue), jamais `redirect`, qui perdrait le formulaire.
import "server-only";

import { ApiError } from "@jeflink/api-client";
import { type BffServer, createBff } from "@jeflink/api-client/bff";
import { safeNextPath } from "@jeflink/api-client/paths";
import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { LOGIN_PATH, PATH_HEADER, readBffConfig } from "./bff-config";

type Bff = ReturnType<typeof createBff>;

// Configuration figée au premier usage (validée au démarrage par src/instrumentation.ts). Aucun
// état de requête ici : jetons et en-têtes restent propres à chaque requête.
let instance: Bff | undefined;

export function bff(): Bff {
  instance ??= createBff(readBffConfig(process.env));
  return instance;
}

/** Chemin de la page courante, posé par src/proxy.ts ; revalidé avant toute redirection. */
async function currentPath(): Promise<string> {
  return safeNextPath((await headers()).get(PATH_HEADER));
}

/** Contexte serveur de la requête courante : rien de secret n'y est lisible. */
export async function serverApi(): Promise<BffServer> {
  return bff().server(await headers());
}

/**
 * Page qui exige une session : accès expiré mais refresh possible → page de rebond du BFF, qui
 * revient ici. Les Server Components ne rafraîchissent jamais eux-mêmes (S6).
 */
export async function serverApiWithSession(): Promise<BffServer> {
  const api = await serverApi();
  if (api.needsRefresh) redirect(api.refreshPath(await currentPath()));
  return api;
}

/**
 * Erreur d'un appel serveur. Un 401 alors qu'un accès était présent (session révoquée, compte
 * désactivé) mène à la connexion, jamais au refresh : pas de boucle. Le reste est relancé.
 */
export async function rethrowApiError(error: unknown): Promise<never> {
  if (error instanceof ApiError && error.status === 401) {
    redirect(`${LOGIN_PATH}?next=${encodeURIComponent(await currentPath())}`);
  }
  throw error;
}
