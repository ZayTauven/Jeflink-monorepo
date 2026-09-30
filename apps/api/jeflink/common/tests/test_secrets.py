import importlib

import pytest
from django.core.exceptions import ImproperlyConfigured

from jeflink.common.secrets import check_secrets, secret_problems

LONG = "x" * 40


def test_configuration_de_test_valide():
    assert secret_problems() == []


def test_les_tests_tournent_avec_les_reglages_de_test(settings):
    assert settings.SETTINGS_MODULE == "jeflink.settings.test"
    assert settings.DJANGO_ENV == "test"


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


def test_secret_key_courte_refusee(settings):
    settings.SECRET_KEY = "court"
    assert any(p.startswith("SECRET_KEY") for p in secret_problems())


def test_liste_vide_refusee(settings):
    settings.BFF_SHARED_SECRETS = []
    assert "BFF_SHARED_SECRETS : aucune valeur" in secret_problems()


def test_cle_fernet_invalide(settings):
    settings.MFA_ENCRYPTION_KEYS = ["x" * 44]
    assert "MFA_ENCRYPTION_KEYS[0] : clé Fernet invalide" in secret_problems()


def test_kid_en_double(settings):
    settings.JWT_SIGNING_KEYS_RAW = ["a:" + "k" * 40, "a:" + "j" * 40]
    assert any("kid en double" in p for p in secret_problems())


def test_environnement_inconnu(settings):
    settings.DJANGO_ENV = "prod"
    assert "DJANGO_ENV : valeur inconnue" in secret_problems()


@pytest.mark.parametrize("env", ["staging", "production"])
def test_valeurs_publiques_interdites_hors_local_et_test(settings, env):
    settings.DJANGO_ENV = env
    assert any("valeur publique" in p for p in secret_problems())


def test_message_sans_valeur_de_secret(settings):
    settings.OTP_HMAC_KEY = "valeur-secrete"
    assert all("valeur-secrete" not in p for p in secret_problems())


@pytest.mark.parametrize("module", ["jeflink.settings.production", "jeflink.settings.local"])
def test_reglages_refuses_avec_le_mauvais_environnement(module):
    # DJANGO_ENV vaut « test » ici : ni production.py ni local.py ne doivent se charger.
    with pytest.raises(ImproperlyConfigured):
        importlib.import_module(module)
