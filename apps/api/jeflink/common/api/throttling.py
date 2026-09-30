"""Limitation par IP pour les vues DRF, sur le socle ``common.ratelimit``.

Chaque vue ``AllowAny`` déclare ``rate_limit_scope`` (un test le vérifie, S29). Les portées
et leurs limites vivent dans ``settings.IP_RATE_LIMITS``.
"""

from typing import Any

from django.conf import settings
from rest_framework.request import Request
from rest_framework.throttling import BaseThrottle

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
        limit = Limit(name=f"ip:{scope}", limit=config["limit"], window=config["window"])
        ip = getattr(request._request, "client_ip", None) or "unknown"
        try:
            outcome = consume([(limit, ip)])
        except RateLimitUnavailable as exc:
            if config.get("fail_open", False):
                return True
            raise DomainError("rate_limit_unavailable", status=503) from exc
        self._wait = outcome.retry_after
        return outcome.allowed

    def wait(self) -> float | None:
        return self._wait
