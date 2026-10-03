import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from jeflink.common.client_ip import TrustedClientIpMiddleware, rate_limit_bucket


@pytest.fixture(autouse=True)
def reseau(settings):
    settings.ALLOWED_HOSTS = ["api", "api.jeflink.sn", "testserver"]
    settings.INTERNAL_API_HOSTS = ["api"]
    settings.BFF_TRUSTED_NETWORKS = ["10.0.0.0/8"]


def call(host="api:8000", remote="10.0.0.5", **headers):
    request = RequestFactory().get("/", HTTP_HOST=host, REMOTE_ADDR=remote, **headers)
    response = TrustedClientIpMiddleware(lambda r: HttpResponse())(request)
    return request, response


def ip_of(**kwargs):
    request, response = call(**kwargs)
    assert response.status_code == 200
    return request.client_ip


def secret(settings):
    return settings.BFF_SHARED_SECRETS[0]


def test_remote_addr_par_defaut():
    assert ip_of(remote="41.82.1.9", host="api.jeflink.sn") == "41.82.1.9"


def test_x_forwarded_for_jamais_lu():
    assert ip_of(host="api.jeflink.sn", HTTP_X_FORWARDED_FOR="1.2.3.4") == "10.0.0.5"


def test_ip_du_bff_crue_avec_reseau_hote_et_secret(settings):
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


def test_host_forge_depuis_l_exterieur_ne_suffit_pas(settings):
    """Un client externe qui envoie « Host: api » avec un secret volé n'est pas cru (réseau)."""
    ip = ip_of(
        remote="41.82.1.9",
        HTTP_X_JEFLINK_CLIENT_IP="1.1.1.1",
        HTTP_X_JEFLINK_BFF=secret(settings),
    )
    assert ip == "41.82.1.9"


def test_bff_de_confiance_sans_ip_refuse(settings):
    _, response = call(HTTP_X_JEFLINK_BFF=secret(settings))
    assert response.status_code == 400
    assert b"client_ip_missing" in response.content


def test_bff_de_confiance_ip_invalide_refuse(settings):
    _, response = call(
        HTTP_X_JEFLINK_CLIENT_IP="1.2.3.4, 5.6.7.8", HTTP_X_JEFLINK_BFF=secret(settings)
    )
    assert response.status_code == 400


def test_hote_refuse_sans_erreur(settings):
    assert ip_of(host="evil.example", HTTP_X_JEFLINK_BFF=secret(settings)) == "10.0.0.5"


def test_ipv6_et_ipv4_mappee():
    assert ip_of(remote="2001:db8::1", host="api.jeflink.sn") == "2001:db8::1"
    assert ip_of(remote="::ffff:41.82.1.2", host="api.jeflink.sn") == "41.82.1.2"


@pytest.mark.parametrize(
    ("a", "b", "meme_compteur"),
    [
        ("2001:db8:1:2::1", "2001:db8:1:2:ffff::9", True),  # même /64
        ("2001:db8:1:2::1", "2001:db8:1:3::1", False),
        ("::ffff:41.82.1.2", "41.82.1.2", True),
        ("fe80::1%eth0", "fe80::1", True),
        ("41.82.1.2", "41.82.1.3", False),
    ],
)
def test_compteurs_par_ip(a, b, meme_compteur):
    assert (rate_limit_bucket(a) == rate_limit_bucket(b)) is meme_compteur


def test_ip_introuvable():
    assert rate_limit_bucket("") == "unknown"
