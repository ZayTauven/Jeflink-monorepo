"""Alertes opérationnelles (logger ``jeflink.alerts``), dédoublonnées pour ne jamais inonder.

Aucune donnée personnelle dans les champs : préfixe opérateur, région, code, portée.
"""

import logging
import threading
import time

import redis

from .ratelimit import client

logger = logging.getLogger("jeflink.alerts")
_local_lock = threading.Lock()
_local_last: dict[str, float] = {}


def _emit(code: str, fields: dict[str, object]) -> None:
    details = " ".join(f"{k}={v}" for k, v in fields.items())
    logger.warning("%s %s", code, details)


def alert_local(key: str, every: int, code: str, **fields: object) -> bool:
    """Au plus une alerte par ``every`` secondes et par processus (utilisable sans Redis)."""
    now = time.monotonic()
    with _local_lock:
        if now - _local_last.get(key, -every) < every:
            return False
        _local_last[key] = now
    _emit(code, fields)
    return True


def alert_once(key: str, ttl: int, code: str, **fields: object) -> bool:
    """Au plus une alerte par période ``ttl``, tous processus confondus (Redis).

    Sans Redis, repli sur la limite locale d'une par minute. Renvoie True si émise.
    """
    try:
        # set(nx=True) renvoie None si la clé existe déjà : alerte déjà émise pour la période.
        first = bool(client().set(f"jf:alert:{key}", 1, nx=True, ex=ttl))
    except redis.RedisError:
        return alert_local(key, 60, code, **fields)
    if first:
        _emit(code, fields)
    return first
