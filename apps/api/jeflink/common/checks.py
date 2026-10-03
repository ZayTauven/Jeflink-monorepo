"""Contrôles de déploiement (spec 001 : S7, S9 ; infra 2 et 4).

Lancés par ``manage.py check --deploy`` (première étape de ``bin/start-production``) :

Redis d'auth (sessions actives, limites, blocages) :
- mot de passe de 32 octets au moins, jamais une valeur publique de dev ;
- TLS (``rediss://``) hors des hôtes déclarés privés (``AUTH_REDIS_PRIVATE_HOSTS``), sans
  désactiver la vérification du certificat ;
- ``maxmemory-policy noeviction`` lue sur le serveur (``INFO``, puis ``CONFIG``). Illisible :
  erreur, sauf attestation explicite ``AUTH_REDIS_NOEVICTION_ATTESTED``.

Proxys de confiance :
- ``FORWARDED_ALLOW_IPS`` (IP des nginx dont uvicorn reprend ``X-Forwarded-For``) : adresses
  exactes seulement, jamais une plage, et sans recouvrir ``BFF_TRUSTED_NETWORKS`` ;
- ``USE_X_FORWARDED_HOST`` interdit : ``X-Forwarded-Host: api`` remplirait sinon la condition
  « hôte interne » du BFF.
"""

import ipaddress
from urllib.parse import parse_qs, urlparse

import redis
from django.conf import settings
from django.core.checks import Error, Tags, register

MIN_PASSWORD_BYTES = 32
UNSAFE_TLS_PARAMS = {"ssl_cert_reqs": {"none", "cert_none"}, "ssl_check_hostname": {"false", "0"}}


@register(Tags.security, deploy=True)
def auth_redis_url(app_configs, **kwargs) -> list[Error]:
    url = urlparse(settings.RATELIMIT_REDIS_URL)
    errors = []
    password = url.password or ""
    if len(password.encode()) < MIN_PASSWORD_BYTES or "not-secret" in password:
        errors.append(
            Error(
                "RATELIMIT_REDIS_URL : mot de passe de 32 octets au moins, "
                "jamais une valeur de dev.",
                id="common.E201",
            )
        )
    if url.scheme != "rediss" and url.hostname not in settings.AUTH_REDIS_PRIVATE_HOSTS:
        errors.append(
            Error(
                "RATELIMIT_REDIS_URL : TLS (rediss://) obligatoire hors réseau privé déclaré "
                "(AUTH_REDIS_PRIVATE_HOSTS).",
                id="common.E202",
            )
        )
    query = {key.lower(): value for key, value in parse_qs(url.query).items()}
    for key, forbidden in UNSAFE_TLS_PARAMS.items():
        if any(v.lower() in forbidden for v in query.get(key, [])):
            errors.append(
                Error(
                    f"RATELIMIT_REDIS_URL : {key} désactive la vérification TLS.",
                    id="common.E206",
                )
            )
    return errors


def _eviction_policy() -> str | None:
    """Politique lue sur le serveur : INFO (permis par les Redis gérés), puis CONFIG."""
    from .ratelimit import client

    try:
        policy = client().info("memory").get("maxmemory_policy")
        if policy:
            return str(policy)
    except redis.ResponseError:
        pass
    try:
        return client().config_get("maxmemory-policy").get("maxmemory-policy")
    except redis.ResponseError:
        return None


@register(Tags.security, deploy=True)
def auth_redis_policy(app_configs, **kwargs) -> list[Error]:
    try:
        policy = _eviction_policy()
    except redis.RedisError:
        return [Error("Redis d'auth injoignable.", id="common.E204")]
    if policy is None:
        if settings.AUTH_REDIS_NOEVICTION_ATTESTED:
            return []
        return [
            Error(
                "Redis d'auth : politique d'éviction illisible. Vérifier noeviction chez le "
                "fournisseur, puis poser AUTH_REDIS_NOEVICTION_ATTESTED=1.",
                id="common.E203",
            )
        ]
    if policy != "noeviction":
        return [
            Error(f"Redis d'auth : maxmemory-policy={policy}, noeviction exigé.", id="common.E205")
        ]
    return []


@register(Tags.security, deploy=True)
def trusted_proxies(app_configs, **kwargs) -> list[Error]:
    errors = []
    proxies = []
    for raw in settings.FORWARDED_ALLOW_IPS:
        try:
            network = ipaddress.ip_network(raw.strip(), strict=False)
        except ValueError:
            errors.append(Error(f"FORWARDED_ALLOW_IPS : « {raw} » invalide.", id="common.E301"))
            continue
        if network.num_addresses != 1:
            errors.append(
                Error(
                    f"FORWARDED_ALLOW_IPS : « {raw} » est une plage ; seules les IP exactes des "
                    "reverse proxies sont permises.",
                    id="common.E302",
                )
            )
        proxies.append(network)
    if not proxies and not errors:
        errors.append(Error("FORWARDED_ALLOW_IPS : vide.", id="common.E303"))
    for cidr in settings.BFF_TRUSTED_NETWORKS:
        try:
            bff = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            continue
        if any(proxy.version == bff.version and proxy.overlaps(bff) for proxy in proxies):
            errors.append(
                Error(
                    "FORWARDED_ALLOW_IPS recouvre BFF_TRUSTED_NETWORKS : un proxy de confiance "
                    "pourrait se faire passer pour le BFF.",
                    id="common.E304",
                )
            )
    if getattr(settings, "USE_X_FORWARDED_HOST", False):
        errors.append(Error("USE_X_FORWARDED_HOST est interdit (S9).", id="common.E305"))
    return errors
