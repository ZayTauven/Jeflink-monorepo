import pytest

from jeflink.accounts.sms_templates import otp_sms_body
from jeflink.common.gsm7 import is_gsm7, segments

APPS = ["client", "pro", "web", "console"]
PURPOSES = ["login", "delete_account", "change_phone", "sensitive_action"]


@pytest.fixture(autouse=True)
def hachages(settings):
    settings.SMS_ANDROID_APP_HASH = {"client": "FA+9qCX9VSu", "pro": "Kx8Pq2Lm3Zt"}


@pytest.mark.parametrize("app", APPS)
@pytest.mark.parametrize("purpose", PURPOSES)
@pytest.mark.parametrize("language", ["fr", "wo", "en"])
def test_un_sms_gsm7_avec_le_code(app, purpose, language):
    body = otp_sms_body(app=app, purpose=purpose, code="482913", language=language)
    assert is_gsm7(body)
    assert segments(body) == 1
    assert "482913" in body


def test_gabarits_client_et_pro_distincts():
    client = otp_sms_body(app="client", purpose="login", code="482913")
    pro = otp_sms_body(app="pro", purpose="login", code="482913")
    assert "ni à un artisan" in client and client.endswith("FA+9qCX9VSu")
    assert pro.startswith("Jeflink Pro") and "ni à un client" in pro and pro.endswith("Kx8Pq2Lm3Zt")


def test_ligne_webotp_pour_le_web():
    body = otp_sms_body(app="web", purpose="login", code="482913")
    assert body.splitlines()[-1] == "@jeflink.sn #482913"


@pytest.mark.parametrize("kind", ["invitation", "phone_changed"])
@pytest.mark.parametrize("language", ["fr", "wo"])
def test_sms_d_information_gsm7_un_seul_sms_sans_donnee(kind, language):
    """Chaque gabarit d'information passe en GSM-7 sur un seul SMS (un « ê » le casserait)."""
    from jeflink.accounts.models import NoticeSms
    from jeflink.accounts.sms_templates import notice_sms_body

    assert kind in NoticeSms.Kind.values
    body = notice_sms_body(kind=kind, language=language)
    assert is_gsm7(body) and segments(body) == 1
    assert "+221" not in body
