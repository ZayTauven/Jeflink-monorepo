"""Limitation par IP pour les vues DRF, sur le socle ``common.ratelimit``.

Chaque vue ``AllowAny`` déclare ``rate_limit_scope`` (un test le vérifie, S29). Les portées
et leurs limites vivent dans ``settings.IP_RATE_LIMITS``. Le comptage se fait par
``rate_limit_bucket`` (IPv6 regroupées par /64).
"""

from typing import Any

from django.conf import settings
from rest_framework.request import Request
from rest_framework.throttling import BaseThrottle

from jeflink.common.alerts import alert_local
from jeflink.common.client_ip import UNKNOWN, rate_limit_bucket
from jeflink.common.errors import DomainError
from jeflink.common.ratelimit import Limit, RateLimitUnavailable, consume


class IpRateThrottle(BaseThrottle):
    def __init__(self) -> None:
        self._wait: int | None = None

    def allow_request(self, request: Request, view: Any) -> bool:
        scope = getattr(view, "rate_limit_scope", None)
        if scope is None:
            return True
        config = settings.IP_RATE_LIMITS[scope]
        fail_open = config.get("fail_open", False)
        bucket = rate_limit_bucket(getattr(request._request, "client_ip", "") or "")
        if bucket == UNKNOWN:
            # Sans IP, tous les clients partageraient un compteur : on refuse et on alerte.
            alert_local("client_ip_unknown", 60, "client_ip_unknown", scope=scope)
            if fail_open:
                return True
            raise DomainError("client_ip_unknown", status=503)
        limit = Limit(name=f"ip:{scope}", limit=config["limit"], window=config["window"])
        try:
            outcome = consume([(limit, bucket)])
        except RateLimitUnavailable as exc:
            alert_local("ratelimit_unavailable", 60, "ratelimit_redis_unavailable", scope=scope)
            if fail_open:
                return True
            raise DomainError("rate_limit_unavailable", status=503) from exc
        self._wait = outcome.retry_after
        return outcome.allowed

    def wait(self) -> float | None:
        return self._wait
