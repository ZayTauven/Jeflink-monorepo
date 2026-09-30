# Jeflink — services pro à la demande au Sénégal

Jeflink met en relation particuliers et entreprises avec des pros vérifiés (artisans, techniciens, services à domicile).
Promesse : **le bon pro, au bon prix, travail garanti** — en français et en wolof, par l'app, le web ou WhatsApp.
Lancement V1 : Dakar, 6 métiers (plomberie, électricité, froid & clim, électroménager, ménage, petits travaux). **Métiers et zones sont des données** (`catalog`, `zones`, administrées par l'Ops), jamais des listes en dur : on en ajoute sans toucher au code.
Le template Demandium a été abandonné ; on n'en garde que des idées fonctionnelles (voir `docs/product/PRODUCT.md`).

## Carte du monorepo

```
jeflink/
├── apps/
│   ├── api/        Django 5.2 LTS + DRF + PostGIS + Celery + Channels   → apps/api/CLAUDE.md
│   ├── web/        Next.js (App Router) — site public, SEO, parcours client web (direction Crafto)
│   ├── console/    Next.js (App Router) — back-office Admin + Pro (ossature Vireo « dé-vibecodée »)
│   ├── client/     Expo (Expo Router) — app client
│   └── pro/        Expo (Expo Router) — app Pro unique : prestataire + technicien (rôles)
├── packages/
│   ├── ui-tokens/  design tokens : source unique (CSS vars + TS + preset Tailwind)
│   ├── api-client/ client TS généré depuis l'OpenAPI Django — NE JAMAIS ÉDITER À LA MAIN
│   └── config/     eslint, tsconfig, prettier partagés
├── infra/          docker-compose, scripts
├── docs/           produit, architecture, design, ADR, specs
└── references/     LOCAL, non versionné, lecture seule (hook) : crafto/, vireo/, assets-originaux/, demandium.txt
```

## Commandes

| Besoin                                        | Commande                                                 |
| --------------------------------------------- | -------------------------------------------------------- |
| Lancer postgres/redis/api/worker              | `make up` (puis `make logs`)                             |
| Migrations                                    | `make makemigrations` / `make migrate`                   |
| Tests backend                                 | `make api-test` (pytest)                                 |
| Régénérer le client TS après changement d'API | `make openapi`                                           |
| Front public / console                        | `pnpm dev --filter web` / `pnpm dev --filter console`    |
| Apps mobiles                                  | `pnpm --filter client start` / `pnpm --filter pro start` |
| Lint + typecheck global                       | `pnpm lint && pnpm typecheck`                            |

Turborepo : sa doc embarquée fait foi, voir `AGENTS.md` (bloc géré par turbo).

Poste de dev : Windows 11 (PowerShell + Git Bash). Les hooks `.claude/hooks/*.mjs` sont en Node (ni jq ni bash requis). Si `make`, `pnpm` ou `uv` manquent, voir « Prérequis » dans `README.md` plutôt que de contourner.

## Règles non négociables

1. **Contrat API d'abord.** Tout changement d'endpoint → schéma drf-spectacular → `make openapi` → client régénéré. Aucun `fetch` écrit à la main dans les fronts.
2. **Argent = entier XOF.** Jamais de float ni de décimales. Tout mouvement d'argent passe par le grand livre (`wallet.LedgerEntry`), jamais une mise à jour de solde directe.
3. **Paiements uniquement via `payments.gateways.PaymentGateway`.** Aucun appel direct à un fournisseur (WiiPay arrivera comme adaptateur).
4. **IA uniquement côté serveur, via `apps/api/ai`.** Prompts versionnés, sorties structurées validées, repli humain prévu. Aucun appel LLM depuis un front ou une app.
5. **Téléphone = identifiant principal**, stocké en E.164 (`+221…`). Dates stockées en UTC, affichées en `Africa/Dakar`.
6. **i18n dès le premier écran** : `fr` par défaut, `wo` prévu. Aucune chaîne en dur dans un composant.
7. **Design** : lire `docs/design/DESIGN.md` avant tout travail d'interface. Le skill `jeflink-design` s'applique ; les patterns « vibecodés » listés sont interdits.
8. **Données personnelles** : minimisation. Jamais de pièce d'identité, selfie KYC, numéro complet ou position GPS dans les logs. Conformité à la loi sénégalaise sur les données personnelles (déclarations CDP).
9. **Réseau faible, téléphones modestes** : images redimensionnées (WebP/AVIF), listes paginées, pas de dépendance lourde sans justification écrite dans la PR.
10. **Machine à états des réservations** : aucune transition hors `bookings.services.transition()`. Chaque transition est journalisée.

## Workflow attendu

- Feature non triviale → `/feature <nom>` : spec dans `docs/specs/`, relue par l'agent `terrain-reviewer`, validée par Zay **avant** de coder.
- Décision d'architecture → `/adr <titre>`.
- Avant PR → `/ship-check`.
- « Done » = tests + migrations + schéma OpenAPI + clés i18n + revue design si UI.
- Commits : Conventional Commits, scope = app (`feat(api): …`, `fix(pro): …`).

## Sous-agents (`.claude/agents/`)

| Agent               | Rôle                                                                                          |
| ------------------- | --------------------------------------------------------------------------------------------- |
| `architect`         | Découpe une feature en tâches par couche, écrit specs et ADR. N'écrit pas de code applicatif. |
| `django-api`        | Domaines Django, services, API, tâches Celery, tests.                                         |
| `next-frontend`     | `apps/web` et `apps/console`.                                                                 |
| `expo-mobile`       | `apps/client` et `apps/pro`, hors-ligne, notifications.                                       |
| `ai-engineer`       | Capacités IA dans `apps/api/ai` : prompts, schémas, évals, replis.                            |
| `design-guardian`   | Revue UI contre DESIGN.md (lecture seule).                                                    |
| `terrain-reviewer`  | Revue « réalité Sénégal » : réseau, langues, paiement, adressage, confiance.                  |
| `security-reviewer` | Argent, KYC, auth, permissions, données perso (lecture seule).                                |

## Skills globaux — à utiliser sans hésiter

Beaucoup de skills couvrant la stack sont installés **globalement** sur la machine (`~/.claude/skills`). Chaque agent, principal ou sous-agent, les invoque via l'outil `Skill` dès qu'une tâche entre dans leur champ. Pas besoin de demander.

| Domaine                    | Skills                                                                                                                                                                                                                    |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Django / DRF / PostGIS     | `django-expert`, `django-patterns`, `django-security`                                                                                                                                                                     |
| Next.js (`web`, `console`) | `nextjs-developer`, `shadcn-ui` (console), `frontend-design`, `web-design-guidelines`, `ui-ux-pro-max`, `redesign-existing-projects` (porter Crafto / Vireo)                                                              |
| Expo (`client`, `pro`)     | `building-native-ui`, `native-data-fetching`, `expo-dev-client`, `expo-deployment`, `expo-cicd-workflows`, `upgrading-expo`, `expo-module`, `use-dom`, `expo-tailwind-setup` (seulement si NativeWind est retenu par ADR) |
| IA (API Claude)            | `claude-api` : à charger avant tout code qui touche au SDK Anthropic, aux modèles ou au cache de prompt                                                                                                                   |
| UI, revue, accessibilité   | `design:accessibility-review`, `design:design-critique`, `design:design-system`, `design:design-handoff`, `web-design-guidelines`                                                                                         |
| Copie et textes            | `copywriting` (site public), `design:ux-copy` (micro-copie), `humanizer` (chasser le ton « IA »)                                                                                                                          |
| Sécurité                   | `security-review`, `django-security`                                                                                                                                                                                      |
| Diagrammes                 | `drawio-skill`, `fireworks-tech-graph` (Mermaid reste le format par défaut dans `docs/`)                                                                                                                                  |

**Ordre de priorité en cas de conflit** : `CLAUDE.md` > `docs/design/DESIGN.md` et skills projet `jeflink-*` > skill global. Un skill global propose une méthode ; il ne réécrit pas nos règles (tokens, i18n, argent, budget perf, patterns interdits).

- Skills esthétiques à prendre comme inspiration seulement, jamais contre DESIGN.md : `high-end-visual-design`, `design-taste-frontend`, `minimalist-ui`. Écartés : `gpt-taste` (GSAP lourd), `industrial-brutalist-ui`, `stitch-design-taste` (animations perpétuelles).
- **Hors stack, ne pas utiliser** : `flutter-*`, `firebase-*`, `developing-genkit-*`, `stitch-*`, `remotion`, `react-components` (Vite), `expo-api-routes` (notre backend est Django).

## Où chercher

- Vision, périmètre, verdict Demandium, innovations : `docs/product/PRODUCT.md`
- Architecture, domaines, machine à états : `docs/architecture/ARCHITECTURE.md`
- Direction visuelle : `docs/design/DESIGN.md`
- Décisions : `docs/adr/`
- Références visuelles (locales) : `references/crafto/demo-marketing-strategy.html` (web public), `references/vireo/` (console), `references/assets-originaux/` (logo, illustrations : à optimiser en WebP/AVIF avant tout usage dans une app)
