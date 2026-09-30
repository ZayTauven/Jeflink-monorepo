from types import SimpleNamespace

import pytest
from django.test import RequestFactory
from django.urls import URLPattern, URLResolver, get_resolver, reverse
from rest_framework.permissions import AllowAny
from rest_framework.request import Request

from jeflink.common.api.throttling import IpRateThrottle
from jeflink.common.errors import DomainError


def _walk(patterns):
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from _walk(pattern.url_patterns)
        elif isinstance(pattern, URLPattern):
            yield pattern


def test_chaque_vue_publique_declare_sa_limite(settings):
    """S29 : toute vue AllowAny porte un rate_limit_scope connu."""
    publiques = []
    for pattern in _walk(get_resolver().url_patterns):
        view = getattr(pattern.callback, "view_class", None) or getattr(
            pattern.callback, "cls", None
        )
        if view is None or AllowAny not in getattr(view, "permission_classes", []):
            continue
        publiques.append(view.__name__)
        scope = getattr(view, "rate_limit_scope", None)
        assert scope in settings.IP_RATE_LIMITS, f"{view.__name__} sans limite déclarée"
    assert "HealthView" in publiques


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
