import pytest
from django.core.exceptions import ImproperlyConfigured

from jeflink.common.secrets import check_secrets, secret_problems

LONG = "x" * 40


def test_configuration_de_test_valide():
    assert secret_problems() == []


def test_cle_trop_courte_refusee(settings):
    settings.OTP_HMAC_KEY = "court"
    with pytest.raises(ImproperlyConfigured, match="OTP_HMAC_KEY"):
        check_secrets()


def test_cle_reutilisee_refusee(settings):
    settings.PII_HMAC_KEY = settings.OTP_HMAC_KEY
    assert any("identique à" in p for p in secret_problems())


def test_cle_egale_a_secret_key_refusee(settings):
    settings.SECRET_KEY = LONG
    settings.PII_HMAC_KEY = LONG
    assert any("SECRET_KEY" in p for p in secret_problems())


def test_liste_vide_refusee(settings):
    settings.BFF_SHARED_SECRETS = []
    assert "BFF_SHARED_SECRETS : aucune valeur" in secret_problems()


def test_message_sans_valeur_de_secret(settings):
    settings.OTP_HMAC_KEY = "valeur-secrete"
    assert all("valeur-secrete" not in p for p in secret_problems())


def test_les_tests_tournent_avec_les_reglages_de_test(settings):
    assert settings.SETTINGS_MODULE == "jeflink.settings.test"
    assert settings.DJANGO_ENV == "test"
