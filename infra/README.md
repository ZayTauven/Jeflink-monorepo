# Infra Jeflink

## Local

`make up` lance PostGIS, Redis, le Redis d'auth, le stockage S3 (SeaweedFS), l'API (runserver), un worker Celery et Celery beat (`infra/docker-compose.yml`). En local, ces services tournent en root, parce qu'ils exécutent `uv run` sur le code monté. L'image de production tourne sans privilèges.

## Production et staging — topologie attendue (spec 001, infra 2 à 4)

```
Internet ──TLS──> nginx public (bord)     ──┐
                                            ├──réseau privé──> api (uvicorn) ──> PostGIS, Redis, Redis d'auth
BFF Next ──TLS, https://api──> nginx interne┘
Équipe technique ──VPN ou bastion──> nginx interne (https://api/admin/)
Orchestrateur ──HTTP direct, Host: api──> api:8000/api/health/   (seule exception au TLS)
```

### Bord public

Gabarits `infra/proxy/templates/production/` et `jeflink-api-locations.inc.template`, pour l'image nginx officielle. Le gabarit s'appelle `default.conf` pour remplacer la page d'accueil de l'image. Variables : `API_PUBLIC_HOST`, `API_UPSTREAM`, `TLS_CERT`, `TLS_KEY`.

Le bord public :

- ferme la connexion pour tout hôte inconnu, y compris `api`, réservé au réseau interne ;
- ne sert jamais `/admin/`, `/api/schema/`, `/api/docs/` ni `/api/internal/` ;
- retire les en-têtes `X-Jeflink-*`, ainsi que `Forwarded`, `X-Forwarded-Host`, `X-Forwarded-Port` et `X-Real-IP`, venus de l'extérieur ;
- écrase `X-Forwarded-For` avec l'adresse réelle et impose `X-Forwarded-Proto: https`.

**Répartiteur de charge cloud devant nginx** : `$remote_addr` deviendrait l'IP du répartiteur, et tous les clients partageraient alors les mêmes limites. Dans ce cas, activer le PROXY protocol entre le répartiteur et nginx (`listen … proxy_protocol`, `set_real_ip_from <IP exactes du répartiteur>`, `real_ip_header proxy_protocol`), jamais `X-Forwarded-For` en confiance.

### Écouteur interne (BFF et admin)

Gabarit `infra/proxy/templates/internal/`, en TLS, avec un certificat pour le nom `api` émis par une autorité interne. C'est par lui que passent :

- le BFF Next : `apiUrl = "https://api"`, l'autorité interne étant ajoutée par `NODE_EXTRA_CA_CERTS` ;
- l'admin Django, par VPN ou bastion.

Ainsi, les réglages de production s'appliquent sans exception : redirection HTTPS et cookies `Secure`. Les en-têtes `X-Jeflink-*` du BFF y passent. Django ne les croit que si trois conditions sont réunies : la connexion vient de `BFF_TRUSTED_NETWORKS`, elle arrive par l'hôte `api`, et le secret partagé est valide.

### Sonde de santé

`GET http://api:8000/api/health/`, avec `Host: api`. C'est la seule URL exemptée de la redirection HTTPS (`SECURE_REDIRECT_EXEMPT`).

### API

L'image démarre par `bin/start-production` :

1. `manage.py check --deploy --database default` vérifie les secrets, le Redis d'auth, les proxys de confiance et le compte de revue des stores. Une erreur empêche le démarrage.
2. Lancement d'uvicorn avec `--proxy-headers --forwarded-allow-ips "$FORWARDED_ALLOW_IPS"`.

Variables obligatoires en plus des secrets :

| Variable               | Valeur                                                                                                                                                                 |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ALLOWED_HOSTS`        | hôte public et `api`                                                                                                                                                   |
| `INTERNAL_API_HOSTS`   | `api`                                                                                                                                                                  |
| `BFF_TRUSTED_NETWORKS` | IP ou sous-réseau des instances du BFF, **distinct de celui des nginx**                                                                                                |
| `FORWARDED_ALLOW_IPS`  | IP **exactes** des deux nginx (public et interne). Jamais une plage, jamais `*` ; le contrôle `common.E30x` refuse aussi tout recouvrement avec `BFF_TRUSTED_NETWORKS` |
| `RATELIMIT_REDIS_URL`  | Redis d'auth ; voir ci-dessous                                                                                                                                         |

### Redis d'auth

Instance ou base dédiée. Il porte les sessions actives, les compteurs de limites et les blocages : une éviction rouvrirait une limite ou ferait revivre une session révoquée.

- `maxmemory-policy noeviction`, lue au démarrage par `INFO` ou `CONFIG`. Si le fournisseur interdit les deux, vérifier la politique dans sa console, puis poser `AUTH_REDIS_NOEVICTION_ATTESTED=1`.
- Persistance AOF `appendfsync everysec` : un redémarrage ne remet pas les compteurs à zéro.
- Mot de passe de 32 octets au moins.
- `rediss://` avec vérification du certificat, sauf si l'hôte figure dans `AUTH_REDIS_PRIVATE_HOSTS`.

### Celery

Workers sans `-B`, et **une seule** instance de `celery beat`.

### Migrations

Étape de déploiement séparée (`manage.py migrate`), avant le démarrage des nouvelles instances de l'API.

## Intégration continue

`.github/workflows/ci.yml`, sur toutes les branches. Actions et images épinglées par condensat. Jobs :

- gitleaks sur tout l'historique ;
- API : ruff, migrations à jour et pytest ;
- TypeScript : typecheck, lint et tests ;
- bord public :
  - en-têtes `X-Jeflink-*` retirés ;
  - `nginx -t` sur les gabarits de production et interne ;
  - test de fumée complet, avec nginx devant l'API en réglages de production et un amont « écho » pour contrôler ce que reçoit l'API.

**À configurer dans GitHub** (hors dépôt) : protection de `main`, avec ces jobs déclarés obligatoires.

Pour lancer le test de fumée en local :

```bash
node infra/proxy/run-smoke.mjs
```
