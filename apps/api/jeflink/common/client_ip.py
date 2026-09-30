"""IP cliente fiable pour les limites de débit (spec 001, S9).

- Web et console : le BFF envoie ``X-Jeflink-Client-Ip``. On n'y croit que si le secret BFF
  est valide **et** que la requête arrive par l'hôte interne (``INTERNAL_API_HOSTS``).
- Mobile : ``REMOTE_ADDR``, réglé par le reverse proxy. ``X-Forwarded-For`` n'est jamais lu.
"""

import ipaddress
from collections.abc import Callable

from django.conf import settings
from django.core.exceptions import DisallowedHost
from django.http import HttpRequest, HttpResponse

from .request_context import is_trusted_bff

CLIENT_IP_HEADER = "X-Jeflink-Client-Ip"


def _valid_ip(value: str) -> str:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return ""


def arrives_by_internal_host(request: HttpRequest) -> bool:
    try:
        host = request.get_host()
    except DisallowedHost:
        return False
    return host.rsplit(":", 1)[0].strip("[]").lower() in settings.INTERNAL_API_HOSTS


def resolve_client_ip(request: HttpRequest) -> str:
    if arrives_by_internal_host(request) and is_trusted_bff(request):
        forwarded = _valid_ip(request.headers.get(CLIENT_IP_HEADER, ""))
        if forwarded:
            return forwarded
    return _valid_ip(request.META.get("REMOTE_ADDR", "")) or "unknown"


class TrustedClientIpMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.client_ip = resolve_client_ip(request)
        return self.get_response(request)
