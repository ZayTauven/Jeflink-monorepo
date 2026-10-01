# Infra Jeflink

## Local

`make up` lance PostGIS, Redis, le Redis d'auth, le stockage S3 (SeaweedFS), l'API (runserver), un worker Celery et Celery beat (`infra/docker-compose.yml`).

## Production et staging — topologie attendue (spec 001, infra 2 à 4)

```
Internet ──TLS──> nginx (bord public)  ──réseau privé──> api (uvicorn) ──> PostGIS, Redis, Redis d'auth
                                                          ▲
BFF Next (web, console) ──réseau privé, Host: api─────────┘   (X-Jeflink-Bff + secret)
Équipe technique ──VPN ou bastion, réseau privé──> api/admin/
```

**Bord public** : gabarits `infra/proxy/templates/` (image nginx officielle, variables `API_PUBLIC_HOST`, `API_UPSTREAM`, `TLS_CERT`, `TLS_KEY`). Il :

- ferme la connexion pour tout hôte inconnu, y compris `api`, réservé au réseau interne ;
- ne sert jamais `/admin/`, `/api/schema/`, `/api/docs/` ni `/api/internal/` ;
- retire les en-têtes `X-Jeflink-*` venus de l'extérieur (liste vérifiée en CI par `infra/proxy/check-headers.mjs`) ;
- écrase `X-Forwarded-For` avec l'adresse réelle, sans jamais la compléter.

**API** : l'image démarre par `bin/start-production`, qui :

1. lance `manage.py check --deploy --database default` (secrets, Redis d'auth, compte de revue des stores). Une erreur empêche le démarrage ;
2. démarre uvicorn avec `--proxy-headers --forwarded-allow-ips "$FORWARDED_ALLOW_IPS"`. Seule l'IP du nginx public y figure, jamais `*` : les appels directs du BFF gardent leur adresse réelle, contrôlée par `BFF_TRUSTED_NETWORKS`.

Variables obligatoires en plus des secrets : `ALLOWED_HOSTS` (hôte public et `api`), `INTERNAL_API_HOSTS=api`, `BFF_TRUSTED_NETWORKS` (CIDR du réseau du BFF), `FORWARDED_ALLOW_IPS`, `RATELIMIT_REDIS_URL` (Redis d'auth, avec mot de passe ; `rediss://` sauf si l'hôte figure dans `AUTH_REDIS_PRIVATE_HOSTS`).

**Redis d'auth** : instance ou base dédiée, `maxmemory-policy noeviction`, mot de passe, TLS hors réseau privé. Il porte les sessions actives, les compteurs de limites et les blocages : une éviction rouvrirait une limite ou ferait revivre une session révoquée.

**Celery** : workers sans `-B`, et **une seule** instance de `celery beat`.

**Migrations** : étape de déploiement séparée (`manage.py migrate`), avant le démarrage des nouvelles instances de l'API.

## Vérifier le bord public en local

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.edge.yml up -d edge api-asgi
node infra/proxy/smoke.mjs
```

La CI lance le même test (tâche `edge`).
