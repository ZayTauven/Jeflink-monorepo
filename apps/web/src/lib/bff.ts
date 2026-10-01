// BFF de l'app web (spec 001, web 1 ; ADR 0007). `server-only` : importer ce module depuis un
// Client Component casse le build.
//
// Côté serveur :
// - page : `serverApiWithSession()` (ou `serverApi()` si la session est facultative), puis
//   `options` passé à chaque appel généré ; jamais à un Client Component ni dans un
//   `HydrationBoundary`. Une erreur d'appel passe par `rethrowApiError(error, api)` ;
// - Server Action : `serverApi()` ; si `needsRefresh`, renvoyer `{ needsRefresh: true }` (le client
//   rafraîchit puis rejoue), jamais `redirect`, qui perdrait le formulaire.
import "server-only";

import { type BffServer, createBff } from "@jeflink/api-client/bff";
import { safeNextPath } from "@jeflink/api-client/paths";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { connection } from "next/server";

import { readBffConfig } from "./bff-config.ts";
import { PATH_HEADER } from "./routes.ts";
import { sessionRedirect, unauthorizedRedirect } from "./session-redirects.ts";

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

/**
 * Contexte serveur de la requête courante : rien de secret n'y est lisible. `connection()` rend
 * la page dynamique quoi qu'il arrive : une page qui lit la session n'est jamais prérendue ni
 * mise en cache (revue web 1, I-2).
 */
export async function serverApi(): Promise<BffServer> {
  await connection();
  return bff().server(await headers());
}

/**
 * Page qui exige une session : accès expiré mais refresh possible → page de rebond du BFF, qui
 * revient ici. Les Server Components ne rafraîchissent jamais eux-mêmes (S6).
 */
export async function serverApiWithSession(): Promise<BffServer> {
  const api = await serverApi();
  const target = sessionRedirect(api, await currentPath());
  if (target) redirect(target);
  return api;
}

/** Erreur d'un appel serveur : 401 → refresh ou connexion (voir `unauthorizedRedirect`). */
export async function rethrowApiError(error: unknown, api: BffServer): Promise<never> {
  const target = unauthorizedRedirect(error, api, await currentPath());
  if (target) redirect(target);
  throw error;
}
