"""Limites de débit : fenêtres glissantes dans Redis (spec 001, « Limites de débit », S8).

- Un seul script Lua vérifie **toutes** les limites d'un appel puis les consomme ensemble :
  si l'une est dépassée, rien n'est consommé (aucune limite brûlée pour rien).
- Les identités (numéro, IP, install_id…) ne sont jamais en clair dans Redis : HMAC.
- Redis indisponible : on appelle le repli de l'appelant (comptage en base), sinon on refuse.
  On ne tombe **jamais en mode ouvert**, sauf pour une portée déclarée ``fail_open``.
"""

import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass
from functools import cache

import redis
from django.conf import settings

# KEYS : une clé par limite. ARGV : maintenant (ms), membre unique, puis (limite, fenêtre ms)
# par clé. Renvoie {1, 0} si tout est consommé, sinon {0, index de la limite, attente ms}.
_CONSUME_LUA = """
local now = tonumber(ARGV[1])
local member = ARGV[2]
for i, key in ipairs(KEYS) do
    local limit = tonumber(ARGV[1 + 2 * i])
    local window = tonumber(ARGV[2 + 2 * i])
    redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
    if redis.call('ZCARD', key) + 1 > limit then
        local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
        local wait = window
        if oldest[2] then wait = tonumber(oldest[2]) + window - now end
        return {0, i, wait}
    end
end
for i, key in ipairs(KEYS) do
    local window = tonumber(ARGV[2 + 2 * i])
    redis.call('ZADD', key, now, member)
    redis.call('PEXPIRE', key, window)
end
return {1, 0, 0}
"""


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


def client() -> redis.Redis:
    return _client(settings.RATELIMIT_REDIS_URL)


def consume(checks: list[tuple[Limit, str]]) -> Outcome:
    """Vérifie puis consomme toutes les limites de ``checks`` d'un seul coup (atomique)."""
    if not checks:
        return Outcome(allowed=True)
    keys = [_key(limit, identity) for limit, identity in checks]
    args: list[int | str] = [int(time.time() * 1000), uuid.uuid4().hex]
    for limit, _ in checks:
        args += [limit.limit, limit.window * 1000]
    try:
        allowed, index, wait_ms = client().eval(_CONSUME_LUA, len(keys), *keys, *args)
    except redis.RedisError as exc:
        raise RateLimitUnavailable from exc
    if allowed:
        return Outcome(allowed=True)
    return Outcome(
        allowed=False,
        exceeded=checks[int(index) - 1][0].name,
        retry_after=max(1, -(-int(wait_ms) // 1000)),
    )


def count(limit: Limit, identity: str) -> int:
    """Nombre d'événements encore dans la fenêtre (lecture seule)."""
    key = _key(limit, identity)
    now = int(time.time() * 1000)
    try:
        return int(client().zcount(key, now - limit.window * 1000, "+inf"))
    except redis.RedisError as exc:
        raise RateLimitUnavailable from exc


def reset(limit: Limit, identity: str) -> None:
    try:
        client().delete(_key(limit, identity))
    except redis.RedisError as exc:
        raise RateLimitUnavailable from exc
