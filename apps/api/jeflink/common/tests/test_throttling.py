import contextlib
from types import SimpleNamespace

import pytest
from django.test import RequestFactory
from django.urls import URLPattern, URLResolver, get_resolver, reverse
from rest_framework.permissions import AllowAny, OperandHolder, OperationHolderMixin
from rest_framework.request import Request

from jeflink.common.api.throttling import IpRateThrottle
from jeflink.common.errors import DomainError


def _walk(patterns):
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from _walk(pattern.url_patterns)
        elif isinstance(pattern, URLPattern):
            yield pattern


def _mentions_allow_any(permission) -> bool:
    """AllowAny, directement ou dans une composition (AllowAny | X, ~X…)."""
    if permission is AllowAny or isinstance(permission, AllowAny):
        return True
    if isinstance(permission, OperandHolder | OperationHolderMixin):
        return any(
            _mentions_allow_any(getattr(permission, attr, None))
            for attr in ("op1_class", "op2_class", "op1", "op2", "operand")
        )
    return False


def test_chaque_vue_publique_declare_sa_limite(settings):
    """S29 : toute vue qui admet AllowAny porte une portée connue et garde IpRateThrottle."""
    publiques = []
    for pattern in _walk(get_resolver().url_patterns):
        view_class = getattr(pattern.callback, "view_class", None) or getattr(
            pattern.callback, "cls", None
        )
        if view_class is None:
            continue
        permissions = list(getattr(view_class, "permission_classes", []))
        # Une vue qui surcharge get_permissions est instanciée pour voir ses vraies permissions.
        instance = view_class()
        instance.request = None
        # Une vue dont get_permissions dépend de la requête garde ses classes déclarées.
        with contextlib.suppress(Exception):
            permissions += instance.get_permissions()
        if not any(_mentions_allow_any(p) for p in permissions):
            continue
        publiques.append(view_class.__name__)
        scope = getattr(view_class, "rate_limit_scope", None)
        assert scope in settings.IP_RATE_LIMITS, f"{view_class.__name__} sans limite déclarée"
        assert IpRateThrottle in view_class.throttle_classes, (
            f"{view_class.__name__} a retiré IpRateThrottle"
        )
    assert {"HealthView", "TokenRefreshView"} <= set(publiques)


@pytest.mark.django_db
def test_limite_par_ip_sur_une_vue(client, settings):
    settings.IP_RATE_LIMITS = {**settings.IP_RATE_LIMITS, "health": {"limit": 2, "window": 60}}
    url = reverse("health")
    assert client.get(url, REMOTE_ADDR="10.0.0.1").status_code == 200
    assert client.get(url, REMOTE_ADDR="10.0.0.1").status_code == 200
    refus = client.get(url, REMOTE_ADDR="10.0.0.1")
    assert refus.status_code == 429
    assert refus.json()["code"] == "throttled"
    assert refus.json()["retry_after"] >= 1
    # Une autre IP n'est pas touchée.
    assert client.get(url, REMOTE_ADDR="10.0.0.2").status_code == 200


@pytest.mark.django_db
def test_ipv6_d_un_meme_slash_64_partagent_la_limite(client, settings):
    settings.IP_RATE_LIMITS = {**settings.IP_RATE_LIMITS, "health": {"limit": 1, "window": 60}}
    url = reverse("health")
    assert client.get(url, REMOTE_ADDR="2001:db8:1:2::1").status_code == 200
    assert client.get(url, REMOTE_ADDR="2001:db8:1:2::abcd").status_code == 429


def _request(ip="10.0.0.1"):
    django_request = RequestFactory().get("/")
    django_request.client_ip = ip
    return Request(django_request)


def test_redis_injoignable_refuse_par_defaut(redis_down, settings):
    settings.IP_RATE_LIMITS = {"otp_request": {"limit": 30, "window": 600}}
    view = SimpleNamespace(rate_limit_scope="otp_request")
    with pytest.raises(DomainError) as exc:
        IpRateThrottle().allow_request(_request(), view)
    assert exc.value.status_code == 503


def test_redis_injoignable_ouvert_seulement_si_declare(redis_down, settings):
    settings.IP_RATE_LIMITS = {"health": {"limit": 1, "window": 60, "fail_open": True}}
    view = SimpleNamespace(rate_limit_scope="health")
    assert IpRateThrottle().allow_request(_request(), view)


def test_ip_inconnue_refusee(settings):
    settings.IP_RATE_LIMITS = {"otp_request": {"limit": 30, "window": 600}}
    view = SimpleNamespace(rate_limit_scope="otp_request")
    with pytest.raises(DomainError) as exc:
        IpRateThrottle().allow_request(_request(ip="unknown"), view)
    assert exc.value.code == "client_ip_unknown"
