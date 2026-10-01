# Jeflink

Services pro à la demande au Sénégal. Commencer par `CLAUDE.md`, puis `docs/product/PRODUCT.md`.

## Prérequis

| Outil        | Rôle                                                          | Installation (Windows)                                                               |
| ------------ | ------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Node ≥ 22.13 | fronts, apps, hooks Claude Code                               | déjà présent                                                                         |
| Docker       | postgres/PostGIS, redis, stockage S3 (SeaweedFS), api, worker | déjà présent                                                                         |
| pnpm 12.8.1  | workspaces JS (version figée dans `packageManager`)           | `npm install -g pnpm@12.8.1` (`corepack enable` exige les droits admin sous Windows) |
| uv           | Python de `apps/api` en local (ruff, hook de formatage)       | `scoop install uv` (ou `winget install --id=astral-sh.uv -e`)                        |
| make         | raccourcis du `Makefile`                                      | `scoop install make` (ou `winget install ezwinports.make`)                           |
| gitleaks     | détection de secrets au commit (hook `.githooks/pre-commit`)  | `scoop install gitleaks` ; sinon le hook passe par Docker                            |

`jq` n'est pas nécessaire : les hooks `.claude/hooks/*.mjs` sont en Node.

`pnpm install` active les hooks Git du dépôt (`core.hooksPath = .githooks`) : gitleaks vérifie chaque commit, avec la configuration `.gitleaks.toml`. Sans gitleaks ni Docker, le commit est refusé.

## Démarrage

`make up && make migrate`, puis `make api-test`. L’API répond sur http://localhost:8000/api/health/ (documentation OpenAPI : `/api/docs/`).
`apps/api/.env` est optionnel en local : il ne porte que les secrets (`cp apps/api/.env.example apps/api/.env`).
Dans Claude Code : `/feature <idée>` pour cadrer, puis implémentation avec les agents.

## Matériel de référence

`references/` (local, ignoré par git) contient les templates Crafto et Vireo, les illustrations originales et la liste Demandium. On s'en inspire ; on n'en copie ni le HTML ni le JS.
