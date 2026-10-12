# Jeflink

Services pro à la demande au Sénégal : le bon pro, au bon prix, travail garanti. Démo locale : site public + espace client/pro, sur le template Crafto. Commencer par `CLAUDE.md`, puis `docs/PRODUCT.md`.

## Prérequis

| Outil        | Rôle                                          | Installation (Windows)                      |
| ------------ | --------------------------------------------- | ------------------------------------------- |
| Node ≥ 22.13 | site Next.js, hooks Claude Code               | déjà présent                                |
| pnpm 12.8.1  | dépendances JS                                | `npm install -g pnpm@12.8.1`                |
| uv           | Python 3.13 et dépendances de l'API           | `scoop install uv`                          |
| make         | raccourcis du `Makefile` (facultatif)         | `scoop install make`                        |
| gitleaks     | détection de secrets au commit (dépôt public) | `scoop install gitleaks` (sinon via Docker) |

Le template **Crafto** doit être présent dans `references/crafto` (copie locale, licence Envato, jamais versionnée) : le site en recopie les CSS, JS et images au lancement.

Ni Docker, ni Postgres, ni Redis : l'API tourne sur SQLite.

## Démarrage

```bash
make install
make demo
```

Puis, dans deux terminaux :

```bash
make api
```

```bash
make web
```

- Site : http://localhost:3000
- Console d'administration : http://localhost:3000/console (compte équipe)
- API (documentation interactive) : http://localhost:8000/api/docs/
- Admin Django (maintenance) : http://localhost:8000/admin/

Sans `make` : `uv run --directory apps/api python manage.py migrate`, `… seed_demo`, `… runserver 8000`, puis `pnpm install` et `pnpm dev`.

Le site et la console ont besoin des templates sous licence Envato, à placer localement (jamais versionnés) : `references/crafto` et `references/vireo`. `pnpm dev` en copie les fichiers utiles.

## Démo

`make demo` crée 6 métiers, 22 quartiers de Dakar, des comptes et des demandes à chaque étape (ouverte avec devis, réservée, terminée et notée), plus 90 jours d'historique inventé (clients en `@clients.jeflink.local`, 3 pros à vérifier en `@pros.jeflink.local`) pour les graphiques de la console. **Tous les comptes de démo ont le mot de passe `jeflink-demo`** (valeur locale de test, définie dans `apps/api/jeflink/jobs/management/commands/seed_demo.py`).

| Compte                    | Rôle                                                           |
| ------------------------- | -------------------------------------------------------------- |
| `awa@demo.jeflink.sn`     | cliente : une fuite avec 2 devis à comparer                    |
| `moussa@demo.jeflink.sn`  | client : une demande d'électricité sans devis                  |
| `ibou@demo.jeflink.sn`    | électricien vérifié : peut chiffrer la demande de Moussa       |
| `mamadou@demo.jeflink.sn` | plombier vérifié (aussi `ousmane`, `cheikh`, `fatou`, `aliou`) |
| `admin@jeflink.local`     | équipe Jeflink : console `/console` (et admin Django)          |

Un pro qui s'inscrit sur le site doit être **vérifié** par l'équipe (console → Pros → « Vérifier ») avant de pouvoir envoyer un devis.

Remettre les demandes à zéro : `make demo-reset`.

## Ancienne version

L'architecture précédente (OTP, BFF, PostGIS, Celery, wallet, specs et ADR) est conservée au tag `archive/avant-simplification`.
