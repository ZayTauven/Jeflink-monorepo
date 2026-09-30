"""IP cliente fiable pour les limites de débit (spec 001, S9).

- Web et console : le BFF envoie ``X-Jeflink-Client-Ip``. On n'y croit que si **trois**
  conditions sont réunies : la connexion vient d'un réseau interne déclaré
  (``BFF_TRUSTED_NETWORKS``, propriété réseau que le client ne choisit pas), l'en-tête ``Host``
  est un hôte interne, et le secret BFF est valide.
- Mobile : ``REMOTE_ADDR``, réglé par le reverse proxy. ``X-Forwarded-For`` n'est jamais lu.
- Pour compter, ``rate_limit_bucket`` regroupe une IPv6 par /64 (un client en dispose d'un
  entier) et ramène une IPv4 mappée à son IPv4.
"""

import ipaddress
import json
import logging
from collections.abc import Callable

from django.conf import settings
from django.core.exceptions import DisallowedHost
from django.http import HttpRequest, HttpResponse

from .request_context import BFF_SECRET_HEADER, is_trusted_bff

CLIENT_IP_HEADER = "X-Jeflink-Client-Ip"
UNKNOWN = "unknown"
alerts = logging.getLogger("jeflink.alerts")


def _parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        ip = ipaddress.ip_address(value.strip().split("%", 1)[0])  # sans identifiant de zone
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def rate_limit_bucket(ip: str) -> str:
    """Identité de comptage : IPv4 telle quelle, IPv6 ramenée à son /64."""
    parsed = _parse_ip(ip)
    if parsed is None:
        return UNKNOWN
    if isinstance(parsed, ipaddress.IPv6Address):
        return str(ipaddress.ip_network(f"{parsed}/64", strict=False).network_address) + "/64"
    return str(parsed)


def _from_trusted_network(request: HttpRequest) -> bool:
    remote = _parse_ip(request.META.get("REMOTE_ADDR", ""))
    if remote is None:
        return False
    return any(
        remote in ipaddress.ip_network(cidr, strict=False) for cidr in settings.BFF_TRUSTED_NETWORKS
    )


def arrives_by_internal_host(request: HttpRequest) -> bool:
    try:
        host = request.get_host()
    except DisallowedHost:
        return False
    return host.rsplit(":", 1)[0].strip("[]").lower() in settings.INTERNAL_API_HOSTS


def is_trusted_bff_request(request: HttpRequest) -> bool:
    return (
        _from_trusted_network(request)
        and arrives_by_internal_host(request)
        and is_trusted_bff(request)
    )


def resolve_client_ip(request: HttpRequest) -> str | None:
    """IP cliente, ``unknown`` si introuvable, None si le BFF de confiance n'en fournit pas."""
    if is_trusted_bff_request(request):
        forwarded = _parse_ip(request.headers.get(CLIENT_IP_HEADER, ""))
        return str(forwarded) if forwarded else None
    remote = _parse_ip(request.META.get("REMOTE_ADDR", ""))
    return str(remote) if remote else UNKNOWN


class TrustedClientIpMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        ip = resolve_client_ip(request)
        if ip is None:
            # BFF authentifié sans IP valide : défaut de configuration, jamais d'IP partagée.
            alerts.warning("bff_client_ip_missing header=%s", BFF_SECRET_HEADER)
            return HttpResponse(
                json.dumps({"code": "client_ip_missing"}),
                status=400,
                content_type="application/json",
            )
        request.client_ip = ip
        return self.get_response(request)
