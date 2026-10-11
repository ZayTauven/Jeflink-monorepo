# Jeflink — services pro à la demande au Sénégal

Jeflink met en relation particuliers et entreprises avec des pros vérifiés (plomberie, électricité, froid & clim, électroménager, ménage, petits travaux).
Promesse : **le bon pro, au bon prix, travail garanti**.

**Cap actuel (depuis le 2026-10-11) : une démo locale simple et fonctionnelle.** On a volontairement abandonné l'architecture précédente (OTP, BFF, PostGIS, Celery, Redis, S3, wallet, i18n, apps mobiles) : elle reste consultable au tag git `archive/avant-simplification`. On ne la réintroduit pas morceau par morceau sans décision de Zay.

## Carte du dépôt

```
jeflink/
├── apps/
│   ├── api/   Django 5.2 + DRF + SQLite : comptes, métiers/quartiers, demandes/devis/avis  → apps/api/CLAUDE.md
│   └── web/   Next.js (App Router) : site public + espace client/pro, template Crafto      → apps/web/CLAUDE.md
├── docs/      PRODUCT.md (vision), ARCHITECTURE.md (état actuel), DESIGN.md (direction Crafto)
└── references/  LOCAL, non versionné, lecture seule (hook) : crafto/, assets-originaux/…
```

## Commandes

| Besoin                                   | Commande                        |
| ---------------------------------------- | ------------------------------- |
| Première installation (API + web + démo) | `make install` puis `make demo` |
| Lancer l'API (http://localhost:8000)     | `make api`                      |
| Lancer le site (http://localhost:3000)   | `make web` (ou `pnpm dev`)      |
| Tests API                                | `make test`                     |
| Données de démo remises à zéro           | `make demo-reset`               |
| Typecheck du site                        | `pnpm typecheck`                |

Poste de dev : Windows 11 (PowerShell + Git Bash). Prérequis : `README.md`.

## Règles

1. **Simple d'abord.** Pas de nouvelle dépendance, de nouveau service ou de nouvelle couche sans besoin réel pour la démo. Trois lignes claires valent mieux qu'une abstraction.
2. **Design = template Crafto « Marketing strategy » pris tel quel** (balisage, classes, CSS, JS, images), récit adapté à Jeflink. Lire `docs/DESIGN.md` avant tout travail d'interface. Les fichiers Crafto ne sont jamais versionnés (licence Envato, dépôt public) : `pnpm --filter web crafto` les copie depuis `references/crafto`.
3. **Logo** : le logo provisoire dessiné d'après `references/assets-originaux/concept logo jeflink.jpg` (`apps/web/src/components/logo.tsx`). Jamais un logo tiers (Orange Money, Wave…).
4. **Argent = entier F CFA** (XOF). Jamais de float ni de décimales.
5. **Statut d'une demande** : ne change que par `jobs.services` (`transition()`), chaque changement est journalisé (`RequestEvent`).
6. **Auth** : email + mot de passe (jeton DRF), jeton gardé côté serveur Next dans un cookie httpOnly. La connexion OTP par téléphone viendra avec l'app mobile.
7. **Téléphone** stocké en E.164 (`+221…`), visible de l'autre partie seulement après réservation. Dates en UTC, affichées en `Africa/Dakar`.
8. **Français uniquement** pour la démo (wolof plus tard). Typographie française : espace insécable avant `? ! : ;`.
9. **Secrets** : Claude peut lire et modifier les `.env*`, mais n'en expose ni n'en sauvegarde jamais les valeurs (réponses, commits, docs, mémoire, artifacts, sous-agents). Pour vérifier une clé : présence, longueur ou ✓.
10. Les besoins de production (Postgres, HTTPS, limites de débit, e-mails…) vont dans `docs/ARCHITECTURE.md › Après la démo`, pas dans le code de la démo.

## Workflow

- Commits : Conventional Commits, scope = app (`feat(api): …`, `fix(web): …`).
- « Fini » = `make test` vert, `pnpm typecheck` vert, parcours vérifié dans le navigateur.
- Revue d'interface : agent `design-guardian` ; parcours utilisateurs : `terrain-reviewer` ; auth/permissions/données perso : `security-reviewer`.

## Skills globaux utiles

`django-expert`, `django-security` (API) ; `nextjs-developer`, `web-design-guidelines`, `design:accessibility-review` (web) ; `copywriting`, `design:ux-copy`, `humanizer` (textes). En cas de conflit : `CLAUDE.md` > `docs/DESIGN.md` > skill global.
