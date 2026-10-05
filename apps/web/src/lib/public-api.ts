// `publicApi()` : l'accès des pages publiques (`app/(site)`) à l'API (spec 006, web 2 ; ADR 0013).
// `server-only`. À utiliser à la place de `serverApi()`, qui est réservé aux pages avec session.
//
//   const api = publicApi();
//   const trades = await catalogTradesList(api.options);
//
// - `GET` seulement, sur `/api/catalog/`, `/api/zones/` et `/api/stats/` ; tout autre chemin est
//   refusé avant l'envoi.
// - Aucun cookie, jeton ni en-tête du visiteur, aucune lecture de `headers()` ni de `cookies()` :
//   voir `public-api-core.ts` pour la liste exacte des en-têtes.
// - Cache de données de Next : `fetch` avec `next: { revalidate: 300, tags }`. Ce n'est pas
//   `"use cache"` : il exige `cacheComponents` (coquille prérendue), incompatible avec le rendu à
//   la requête que la CSP à nonce impose. Le cache de données du `fetch` marche dans une page
//   dynamique, une seule entrée pour tous les visiteurs, étiquetée pour `revalidateTag`.
// - Dernière copie servie si l'API ne répond pas (copie mémoire du processus, en plus du cache).
//
// À brancher quand `packages/api-client` sera régénéré (aucun appel ici d'ici là) :
//   `zones/{slug}/` (étiquette zones), `catalog/coverage/` (catalog), `stats/` (stats).
import "server-only";

import { createPublicTransport, type PublicApiSettings } from "./public-api-core.ts";
import { readBffConfig } from "./bff-config.ts";

export {
  isNotFoundError,
  PUBLIC_PREFIXES,
  PUBLIC_REQUEST_HEADERS,
  PUBLIC_REVALIDATE_SECONDS,
} from "./public-api-core.ts";

type PublicApi = {
  readonly options: { readonly transport: ReturnType<typeof createPublicTransport> };
};

let instance: PublicApi | undefined;

function settings(): PublicApiSettings {
  const config = readBffConfig(process.env);
  return { apiUrl: config.apiUrl };
}

/** Options à passer à chaque fonction générée : `catalogTradesList(publicApi().options)`. */
export function publicApi(): PublicApi {
  instance ??= Object.freeze({
    options: Object.freeze({ transport: createPublicTransport(settings()) }),
  });
  return instance;
}
