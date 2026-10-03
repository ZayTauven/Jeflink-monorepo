"""Limites de débit : fenêtres glissantes dans Redis (spec 001, « Limites de débit », S8).

- Un seul script Lua vérifie **toutes** les limites d'un appel puis les consomme ensemble :
  si l'une est dépassée, rien n'est consommé (aucune limite brûlée pour rien).
- L'horloge est celle de Redis (``TIME``) : aucun décalage entre workers.
- Les identités (numéro, IP, install_id…) ne sont jamais en clair dans Redis : HMAC.
- Redis indisponible : on appelle le repli de l'appelant (comptage en base), sinon on refuse.
  On ne tombe **jamais en mode ouvert**, sauf pour une portée déclarée ``fail_open``.
- Redis Cluster non pris en charge : les clés d'un même appel n'ont pas de hash tag commun.
"""

import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass
from functools import cache

import redis
from django.conf import settings

_NOW_MS = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
"""

# KEYS : une clé par limite. ARGV : membre unique, puis (limite, fenêtre ms) par clé.
# Renvoie {1, 0, 0} si tout est consommé, sinon {0, index de la limite, attente ms}.
_CONSUME_LUA = (
    _NOW_MS
    + """
local member = ARGV[1]
for i, key in ipairs(KEYS) do
    local limit = tonumber(ARGV[2 * i])
    local window = tonumber(ARGV[2 * i + 1])
    redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
    if redis.call('ZCARD', key) + 1 > limit then
        local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
        local wait = window
        if oldest[2] then wait = tonumber(oldest[2]) + window - now end
        return {0, i, wait}
    end
end
for i, key in ipairs(KEYS) do
    redis.call('ZADD', key, now, member)
    redis.call('PEXPIRE', key, tonumber(ARGV[2 * i + 1]))
end
return {1, 0, 0}
"""
)

# Ajoute un événement ; si le seuil est atteint, vide la fenêtre et renvoie 1 à CE seul appelant.
_THRESHOLD_LUA = (
    _NOW_MS
    + """
local window = tonumber(ARGV[2])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
redis.call('ZADD', KEYS[1], now, ARGV[1])
redis.call('PEXPIRE', KEYS[1], window)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[3]) then
    redis.call('DEL', KEYS[1])
    return 1
end
return 0
"""
)

# Nombre d'événements dans la fenêtre, avec la même borne que _CONSUME_LUA.
_COUNT_LUA = (
    _NOW_MS
    + """
return redis.call('ZCOUNT', KEYS[1], '(' .. (now - tonumber(ARGV[1])), '+inf')
"""
)


class RateLimitUnavailable(Exception):
    """Redis ne répond pas : l'appelant replie sur la base ou refuse (jamais d'ouverture)."""


@dataclass(frozen=True)
class Limit:
    """``limit`` événements au plus sur ``window`` secondes glissantes, par identité."""

    name: str
    limit: int
    window: int


@dataclass(frozen=True)
class Outcome:
    allowed: bool
    exceeded: str = ""  # nom de la limite dépassée
    retry_after: int = 0  # secondes


def pseudonymize(value: str) -> str:
    key = settings.PII_HMAC_KEY.encode()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()[:32]


def _key(limit: Limit, identity: str) -> str:
    return f"jf:rl:{limit.name}:{pseudonymize(identity)}"


@cache
def _client(url: str) -> redis.Redis:
    return redis.Redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5)


@cache
def _scripts(url: str) -> dict[str, redis.commands.core.Script]:
    connection = _client(url)
    return {
        "consume": connection.register_script(_CONSUME_LUA),
        "threshold": connection.register_script(_THRESHOLD_LUA),
        "count": connection.register_script(_COUNT_LUA),
    }


def client() -> redis.Redis:
    return _client(settings.RATELIMIT_REDIS_URL)


def _script(name: str):
    return _scripts(settings.RATELIMIT_REDIS_URL)[name]


def consume(checks: list[tuple[Limit, str]]) -> Outcome:
    """Vérifie puis consomme toutes les limites de ``checks`` d'un seul coup (atomique)."""
    if not checks:
        return Outcome(allowed=True)
    keys = [_key(limit, identity) for limit, identity in checks]
    args: list[int | str] = [uuid.uuid4().hex]
    for limit, _ in checks:
        args += [limit.limit, limit.window * 1000]
    try:
        allowed, index, wait_ms = _script("consume")(keys=keys, args=args)
    except redis.RedisError as exc:
        raise RateLimitUnavailable from exc
    if allowed:
        return Outcome(allowed=True)
    return Outcome(
        allowed=False,
        exceeded=checks[int(index) - 1][0].name,
        retry_after=max(1, -(-int(wait_ms) // 1000)),
    )


def hit_threshold(limit: Limit, identity: str) -> bool:
    """Compte un événement ; renvoie True à l'unique appelant qui atteint ``limit.limit``.

    La fenêtre est alors vidée : sous concurrence, un seul déclenchement par seuil.
    """
    try:
        triggered = _script("threshold")(
            keys=[_key(limit, identity)],
            args=[uuid.uuid4().hex, limit.window * 1000, limit.limit],
        )
    except redis.RedisError as exc:
        raise RateLimitUnavailable from exc
    return bool(triggered)


def count(limit: Limit, identity: str) -> int:
    """Nombre d'événements encore dans la fenêtre (lecture seule)."""
    try:
        return int(_script("count")(keys=[_key(limit, identity)], args=[limit.window * 1000]))
    except redis.RedisError as exc:
        raise RateLimitUnavailable from exc


def reset(limit: Limit, identity: str) -> None:
    try:
        client().delete(_key(limit, identity))
    except redis.RedisError as exc:
        raise RateLimitUnavailable from exc


def _bucket_key(name: str, identity: str, window: int) -> str:
    bucket = int(time.time()) // window
    return f"jf:ctr:{name}:{pseudonymize(identity)}:{bucket}"


def incr_counter(name: str, identity: str, window: int) -> int:
    """Compteur à fenêtre fixe (INCR + EXPIRE) : mémoire bornée, pour métriques et ratios."""
    key = _bucket_key(name, identity, window)
    try:
        pipe = client().pipeline()
        pipe.incr(key)
        pipe.expire(key, window * 2)
        value, _ = pipe.execute()
    except redis.RedisError as exc:
        raise RateLimitUnavailable from exc
    return int(value)


def get_counter(name: str, identity: str, window: int) -> int:
    try:
        return int(client().get(_bucket_key(name, identity, window)) or 0)
    except redis.RedisError as exc:
        raise RateLimitUnavailable from exc
