import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from jeflink.common.client_ip import TrustedClientIpMiddleware


@pytest.fixture(autouse=True)
def hotes(settings):
    settings.ALLOWED_HOSTS = ["api", "api.jeflink.sn", "testserver"]
    settings.INTERNAL_API_HOSTS = ["api"]


def ip_of(host="api:8000", remote="10.0.0.5", **headers):
    request = RequestFactory().get("/", HTTP_HOST=host, REMOTE_ADDR=remote, **headers)
    TrustedClientIpMiddleware(lambda r: HttpResponse())(request)
    return request.client_ip


def secret(settings):
    return settings.BFF_SHARED_SECRETS[0]


def test_remote_addr_par_defaut():
    assert ip_of() == "10.0.0.5"


def test_x_forwarded_for_jamais_lu():
    assert ip_of(HTTP_X_FORWARDED_FOR="1.2.3.4") == "10.0.0.5"


def test_ip_du_bff_crue_avec_secret_et_hote_interne(settings):
    ip = ip_of(HTTP_X_JEFLINK_CLIENT_IP="41.82.1.2", HTTP_X_JEFLINK_BFF=secret(settings))
    assert ip == "41.82.1.2"


def test_second_secret_de_rotation_accepte(settings):
    settings.BFF_SHARED_SECRETS = ["premier-secret-" + "a" * 30, "second-secret-" + "b" * 30]
    ip = ip_of(HTTP_X_JEFLINK_CLIENT_IP="41.82.1.2", HTTP_X_JEFLINK_BFF="second-secret-" + "b" * 30)
    assert ip == "41.82.1.2"


def test_ip_du_bff_ignoree_sans_secret_valide():
    assert ip_of(HTTP_X_JEFLINK_CLIENT_IP="41.82.1.2", HTTP_X_JEFLINK_BFF="faux") == "10.0.0.5"
    assert ip_of(HTTP_X_JEFLINK_CLIENT_IP="41.82.1.2") == "10.0.0.5"


def test_ip_du_bff_ignoree_hors_hote_interne(settings):
    ip = ip_of(
        host="api.jeflink.sn",
        HTTP_X_JEFLINK_CLIENT_IP="41.82.1.2",
        HTTP_X_JEFLINK_BFF=secret(settings),
    )
    assert ip == "10.0.0.5"


def test_hote_refuse_sans_erreur(settings):
    assert ip_of(host="evil.example", HTTP_X_JEFLINK_BFF=secret(settings)) == "10.0.0.5"


def test_ip_invalide_ignoree(settings):
    ip = ip_of(HTTP_X_JEFLINK_CLIENT_IP="1.2.3.4, 5.6.7.8", HTTP_X_JEFLINK_BFF=secret(settings))
    assert ip == "10.0.0.5"


def test_ipv6():
    assert ip_of(remote="2001:db8::1") == "2001:db8::1"
