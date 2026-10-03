import pytest
from django.core.exceptions import ImproperlyConfigured

from jeflink.notifications.sms import check_sms_settings, get_sms_gateway
from jeflink.notifications.sms.fake import FakeSmsGateway

BODY = "Jeflink : votre code de connexion est 482913. Ne le donnez a personne."


@pytest.fixture(autouse=True)
def boite_vide():
    FakeSmsGateway.reset()
    yield
    FakeSmsGateway.reset()


def send(gateway, key="k1", body=BODY):
    return gateway.send(to="+221771234567", body=body, idempotency_key=key, sender_id="JEFLINK")


def test_fake_en_test_enregistre_sans_afficher(capsys):
    result = send(get_sms_gateway())
    assert result.gateway == "fake"
    assert result.segments == 1
    assert [sms.body for sms in FakeSmsGateway.outbox] == [BODY]
    assert capsys.readouterr().out == ""


def test_fake_idempotent():
    gateway = get_sms_gateway()
    assert send(gateway, "k1") == send(gateway, "k1")
    send(gateway, "k2")
    assert len(FakeSmsGateway.outbox) == 2


def test_fake_affiche_en_local(settings, capsys):
    settings.DJANGO_ENV = "local"
    send(get_sms_gateway())
    assert "482913" in capsys.readouterr().out


def test_segments_comptes():
    assert send(get_sms_gateway(), body="ë" * 71).segments == 2


@pytest.mark.parametrize("env", ["staging", "production"])
def test_fake_interdit_hors_local_et_test(settings, env):
    settings.DJANGO_ENV = env
    settings.DEBUG = True  # DEBUG ne change rien (S23)
    with pytest.raises(ImproperlyConfigured, match="interdit"):
        check_sms_settings()
    with pytest.raises(ImproperlyConfigured):
        get_sms_gateway()


def test_adaptateur_inconnu(settings):
    settings.SMS_GATEWAY = "twilio-maison"
    with pytest.raises(ImproperlyConfigured, match="inconnu"):
        check_sms_settings()


def test_adaptateur_absent(settings):
    settings.SMS_GATEWAY = ""
    check_sms_settings()
    with pytest.raises(ImproperlyConfigured):
        get_sms_gateway()
