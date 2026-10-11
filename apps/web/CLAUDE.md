# apps/web — site public + espace client/pro

Next.js (App Router), **template Crafto « Marketing strategy » pris tel quel** : mêmes balisages, classes, CSS, JS jQuery et images ; seul le récit est adapté. Lire `docs/DESIGN.md`.

- `public/crafto/` est copié depuis `references/crafto` par `scripts/sync-crafto.mjs` (lancé par `pnpm dev`/`build`, ou `pnpm --filter web crafto`). Jamais versionné, jamais modifié à la main : nos ajouts vont dans `public/jeflink.css`.
- Les scripts Crafto sont chargés **après** l'hydratation React (`components/crafto-scripts.tsx`), qui rejoue `window.load`. Conséquences :
  - navigation par `<a href>` (rechargement complet), jamais `next/link` ;
  - pas de `router.refresh()` ni de Server Action qui re-rendrait une page déjà animée par Crafto ;
  - un bouton d'envoi n'a jamais la classe `submit` (main.js l'intercepte).
- Pour porter une section Crafto : partir du HTML du template, garder les classes et `data-*` à l'identique, utiliser les petits composants de `components/crafto.tsx` (`SwitchLink`, `Pill`, `ArrowSwipe`, animations `data-anime`…).
- Données : Server Components + `lib/api.ts` (serveur uniquement). Le jeton DRF vit dans le cookie httpOnly `jeflink_token` ; il n'atteint jamais le navigateur.
- Formulaires : `<ActionForm action="/act/…">` (client) → route handler dans `src/app/act/` → API Django → JSON (avec JS) ou redirection 303 (sans JS).
- Pages : `/`, `/a-propos`, `/services` (comment ça marche), `/metiers`, `/metiers/[slug]`, `/contact`, `/connexion`, `/inscription`, `/espace`, `/espace/demandes/nouvelle`, `/espace/demandes/[id]`.
- Montants via `formatXOF`, dates via `formatDate` (heure de Dakar).

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
