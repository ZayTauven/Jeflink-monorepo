# apps/web — site public + parcours client web

Next.js App Router, Tailwind + preset `@jeflink/ui-tokens`, next-intl (`fr`, `wo`), client API `@jeflink/api-client`.
Direction visuelle : **Crafto** (voir `docs/design/DESIGN.md`, section « Web public »).

- Server Components par défaut ; `"use client"` seulement pour l'interactivité réelle.
- **BFF** (spec 001, ADR 0007) : `src/app/api/[...path]/route.ts` monte `@jeflink/api-client/bff`. Côté serveur, un appel API passe `(await serverApi()).options` (ou `serverApiWithSession()` pour une page qui exige une session), jamais un jeton ; erreur d'appel → `rethrowApiError(error, api)`. Server Action : sur `needsRefresh`, renvoyer `{ needsRefresh: true }`, jamais `redirect`. Côté client, `Providers` configure le client (même origine, refresh sous verrou entre onglets) ; déconnexion par `logoutWebSession()` de `@jeflink/api-client/web`. Variables serveur : `.env.example`, jamais en `NEXT_PUBLIC_`.
- `skipTrailingSlashRedirect` est voulu (barre finale exigée par Django) ; `src/proxy.ts` ramène les pages à leur forme sans barre.
- SEO = canal d'acquisition majeur : pages `/[metier]/[quartier]` (ex. `/plombier/ouakam`) générées depuis catalog × zones, `generateMetadata`, sitemap dynamique, JSON-LD `Service` / `LocalBusiness`.
- Budget perf : LCP < 2,5 s en 3G rapide simulée, JS initial < 150 ko gz par page publique. `next/image` obligatoire.
- Pas de vidéo hero lourde en autoplay sur mobile (image poster + lecture à la demande).
- Photos : artisans et intérieurs sénégalais réels. Aucune image de stock occidentale générique.
- CTA principal toujours double : « Faire une demande » + « Écrire sur WhatsApp ».
