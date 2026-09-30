# ADR 0001 — Monorepo unique

Statut : accepté · 2026-09-30

## Contexte

Cinq applications (api, web, console, client, pro) partagent un contrat d'API, des tokens de design et des règles métier.

## Décision

Un seul dépôt : pnpm workspaces + Turborepo pour le JavaScript, uv pour Python dans `apps/api`. Le client TS est généré depuis l'OpenAPI Django (`packages/api-client`).

## Conséquences

- Un changement d'API casse le build des fronts immédiatement, pas en production.
- Claude Code voit tout le contexte (CLAUDE.md racine + CLAUDE.md par app).
  − CI plus longue : filtrage par app modifiée avec Turborepo.
