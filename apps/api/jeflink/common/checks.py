"""Contrôles de déploiement du Redis d'auth (spec 001, S7 ; infra 2).

Lancés par ``manage.py check --deploy`` (étape obligatoire du déploiement de production) :
- ``RATELIMIT_REDIS_URL`` porte un mot de passe ;
- hors des hôtes déclarés privés (``AUTH_REDIS_PRIVATE_HOSTS``), la connexion est en TLS
  (``rediss://``) ;
- le serveur est en ``maxmemory-policy noeviction`` : une éviction rouvrirait des limites ou
  ferait revivre une session révoquée.
"""

from urllib.parse import urlparse

import redis
from django.conf import settings
from django.core.checks import Error, Tags, Warning, register


@register(Tags.security, deploy=True)
def auth_redis_url(app_configs, **kwargs) -> list[Error]:
    url = urlparse(settings.RATELIMIT_REDIS_URL)
    errors = []
    if not url.password:
        errors.append(Error("RATELIMIT_REDIS_URL : mot de passe obligatoire.", id="common.E201"))
    if url.scheme != "rediss" and url.hostname not in settings.AUTH_REDIS_PRIVATE_HOSTS:
        errors.append(
            Error(
                "RATELIMIT_REDIS_URL : TLS (rediss://) obligatoire hors réseau privé déclaré "
                "(AUTH_REDIS_PRIVATE_HOSTS).",
                id="common.E202",
            )
        )
    return errors


@register(Tags.security, deploy=True)
def auth_redis_policy(app_configs, **kwargs) -> list[Error | Warning]:
    from .ratelimit import client

    try:
        policy = client().config_get("maxmemory-policy").get("maxmemory-policy")
    except redis.ResponseError:
        # Redis géré qui interdit CONFIG : à vérifier dans la console du fournisseur.
        return [
            Warning(
                "Redis d'auth : CONFIG interdit, vérifier maxmemory-policy=noeviction à la main.",
                id="common.W203",
            )
        ]
    except redis.RedisError:
        return [Error("Redis d'auth injoignable.", id="common.E204")]
    if policy != "noeviction":
        return [
            Error(f"Redis d'auth : maxmemory-policy={policy}, noeviction exigé.", id="common.E205")
        ]
    return []
