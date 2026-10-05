# apps/web — site public + parcours client web

Next.js App Router, Tailwind + preset `@jeflink/ui-tokens`, next-intl (`fr`, `wo`), client API `@jeflink/api-client`.
Direction visuelle : **Crafto** (voir `docs/design/DESIGN.md`, section « Web public »).

- Server Components par défaut ; `"use client"` seulement pour l'interactivité réelle.
- **BFF** (spec 001, ADR 0007) : `src/app/api/[...path]/route.ts` monte `@jeflink/api-client/bff`. Côté serveur, un appel API passe `(await serverApi()).options` (ou `serverApiWithSession()` pour une page qui exige une session), jamais un jeton ; erreur d'appel → `rethrowApiError(error, api)`. Server Action : sur `needsRefresh`, renvoyer `{ needsRefresh: true }`, jamais `redirect`. Côté client, `Providers` configure le client (même origine, refresh sous verrou entre onglets) ; déconnexion par `logoutWebSession()` de `@jeflink/api-client/web`. Variables serveur : `.env.example`, jamais en `NEXT_PUBLIC_`.
- `skipTrailingSlashRedirect` est voulu (barre finale exigée par Django) ; `src/proxy.ts` ramène les pages à leur forme sans barre.
- SEO = canal d'acquisition majeur : pages `/[metier]/[quartier]` (ex. `/plombier/ouakam`) générées depuis catalog × zones, `generateMetadata`, sitemap dynamique. JSON-LD `Organization`, `WebSite`, `Service` et `BreadcrumbList`, **jamais `LocalBusiness`** (pas d'adresse ouverte au public par quartier) ni `AggregateRating` (spec 006, Q11).
- Groupes de routes (spec 006, ADR 0013) : `(site)` pour les pages publiques, `(espace)` pour `/connexion`, `/demande` et `/compte` (seul `(espace)` monte `Providers`). Dans `(site)` : aucune lecture de session ni de cookie, langue forcée en `fr`, jamais `serverApi()` ni `serverApiWithSession()` (test d'architecture). Le HTML est le même pour tous les visiteurs.
- `publicApi()` (`src/lib/public-api.ts`) : seul accès à l'API depuis `(site)`. `GET` seulement, 3 préfixes (`/api/catalog/`, `/api/zones/`, `/api/stats/`), en-têtes `Accept` et `Accept-Language: fr` seulement, **sans secret du BFF**, ni cookie, ni jeton, ni en-tête du visiteur. Cache `fetch` (`revalidate: 300`, étiquettes `catalog`, `zones`, `stats`) et copie de secours si l'API échoue. Pas de `"use cache"` : incompatible avec la CSP à nonce.
- Un slug de détail (métier, zone) est toujours résolu contre le catalogue en cache avant tout appel de détail, dans les pages comme dans les images Open Graph : un slug inconnu ne coûte aucun appel. Une erreur de l'API n'est jamais un `notFound()`.
- Budget perf : LCP < 2,5 s en 3G rapide simulée, JS initial < 150 ko gz par page publique. `next/image` obligatoire.
- Pas de vidéo hero lourde en autoplay sur mobile (image poster + lecture à la demande).
- Photos : artisans et intérieurs sénégalais réels. Aucune image de stock occidentale générique.
- CTA principal toujours double : « Faire une demande » + « Écrire sur WhatsApp ».

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
