# ADR 0005 — Socle d'outillage du monorepo

Statut : accepté · 2026-09-30

## Contexte

Mise en route du monorepo sur le poste de dev (Windows 11). Plusieurs choix du kit initial ne tenaient plus en septembre 2026.

## Décision

- **pnpm 12.8.1**, figé exactement dans `packageManager` (`pnpm@9` n'était pas une valeur valide pour corepack).
- **TypeScript `~6.0`**, pas la 7 (port natif) : typescript-eslint exige `typescript < 6.1`. On passera à la 7 quand typescript-eslint la supportera.
- **Hooks Claude Code en Node** (`.claude/hooks/*.mjs`) : ni jq ni bash requis ; sous Windows, `bash` peut désigner WSL.
- **Stockage objets de dev : SeaweedFS** (`chrislusf/seaweedfs`, passerelle S3) à la place de MinIO, qui ne publie plus d'image Docker. L'API ne parle qu'au protocole S3 : le fournisseur de production reste ouvert.
- **Câblage de dev dans `docker-compose.yml`**, secrets seuls dans `apps/api/.env` (optionnel en local).
- **Tokens Tailwind stricts** : `@jeflink/ui-tokens/theme.css` retire les palettes, rayons et ombres par défaut de Tailwind. Seules les classes Jeflink compilent.
- **Utilisateur Django personnalisé** (`accounts.User`) dès la première migration, volontairement minimal en attendant la spec `accounts`.

## Conséquences

- `make up` fonctionne sur un poste neuf sans créer de `.env`.
- Une couleur ou un rayon hors tokens ne peut pas s'écrire en classe Tailwind.
- Le contrat de contraste AA est vérifié à chaque build des tokens.
  − TypeScript 7 (compilation bien plus rapide) est reporté.
  − La migration `accounts.0001` sera réécrite par la spec `accounts` tant que rien n'est déployé.

## Alternatives écartées

- `bitnamilegacy/minio` : image figée, plus maintenue. RustFS : trop jeune.
- Scripts `package.json` à la place de `make` : doublon ; `make` s'installe en une commande (`scoop install make`).
