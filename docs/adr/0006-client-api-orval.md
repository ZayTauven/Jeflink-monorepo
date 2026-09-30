# ADR 0006 — Client API généré avec orval

Statut : accepté · 2026-09-30

## Contexte

Règle 1 : les fronts et apps ne consomment l'API que par un client TS généré depuis l'OpenAPI Django. La console, le web (parcours client) et les apps Expo utilisent TanStack Query.

## Décision

- `packages/api-client` est généré par **orval** (`client: react-query`, `httpClient: fetch`, découpage par tag OpenAPI) depuis `apps/api/schema.yaml`.
- Un seul mutateur écrit à la main, `src/http.ts` (`jeflinkFetch`). C'est le seul `fetch` du monorepo. Chaque app l'initialise avec `configureApiClient()` : cookies httpOnly via le BFF Next pour web et console, jeton bearer pour le mobile.
- Les erreurs sont des `ApiError` qui portent le `code` métier stable renvoyé par Django.
- `make openapi` enchaîne `spectacular` → `schema.yaml` (versionné, pour voir les changements de contrat en revue) → `orval`. `src/generated/` est versionné et protégé en écriture par le hook `guard`.

## Conséquences

- Hooks `useXxx` typés de bout en bout, aucune URL écrite à la main.
- Un changement d'API casse le typecheck des fronts immédiatement.
  − Le code généré est verbeux et alourdit les diffs de PR (fichiers générés à survoler).

## Alternatives écartées

- openapi-typescript + openapi-fetch : plus léger, mais il faudrait écrire à la main chaque hook TanStack Query.
