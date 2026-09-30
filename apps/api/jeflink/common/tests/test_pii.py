import logging

import pytest

from jeflink.common.log_filters import PiiRedactingFilter
from jeflink.common.pii import REDACTED, contains_pii, mask_phone, phone_hmac, redact, redact_data


def test_mask_phone_garde_indicatif_et_deux_chiffres():
    assert mask_phone("+221771234567") == "+221 •••••••67"
    assert mask_phone("+33612345678") == "+33 •••••••78"
    assert mask_phone("") == "•••"


def test_phone_hmac_stable_et_sans_numero():
    assert phone_hmac("+221771234567") == phone_hmac("+221771234567")
    assert phone_hmac("+221771234567") != phone_hmac("+221771234568")
    assert "771234567" not in phone_hmac("+221771234567")


@pytest.mark.parametrize(
    "texte",
    [
        "numéro +221771234567 reçu",
        "numéro 77 123 45 67 reçu",
        "numéro 771234567 reçu",
        "numéro 00221 77 123 45 67 reçu",
        "numéro 76.123.45.67 reçu",
        "numéro 00221771234567 reçu",
        "numéro 221771234567 reçu",
    ],
)
def test_redact_masque_les_formats_senegalais(texte):
    sortie = redact(texte)
    assert REDACTED in sortie
    assert "123" not in sortie


@pytest.mark.parametrize(
    "texte",
    [
        '{"code": "123456"}',
        "code=123456&x=1",
        "Authorization: Bearer abc.def.ghi",
        "refresh='jfr_secret'",
        '"challenge_secret": "s3cr3t"',
        "Cookie: jf_at=abc.def; jf_rt=jfr_secret",
    ],
)
def test_redact_masque_les_cles_sensibles(texte):
    sortie = redact(texte)
    assert REDACTED in sortie
    for fragment in ("123456", "abc.def", "jfr_secret", "s3cr3t"):
        assert fragment not in sortie


def test_redact_laisse_le_texte_ordinaire():
    texte = "demande 42 publiée à Ouakam, barcode=7 et identifiant 1777123456789"
    assert redact(texte) == texte
    assert not contains_pii(texte)


def test_redact_data_recursif():
    donnees = {"phone": "+221771234567", "note": "appeler 77 123 45 67", "n": [{"code": "9"}]}
    assert redact_data(donnees) == {
        "phone": REDACTED,
        "note": f"appeler {REDACTED}",
        "n": [{"code": REDACTED}],
    }


def test_filtre_de_logs_masque_message_et_arguments():
    record = logging.LogRecord(
        "t", logging.INFO, __file__, 1, "OTP pour %s", ("+221771234567",), None
    )
    PiiRedactingFilter().filter(record)
    assert record.getMessage() == f"OTP pour {REDACTED}"


def test_filtre_de_logs_masque_les_exceptions():
    try:
        raise ValueError("numéro +221771234567 invalide")
    except ValueError:
        import sys

        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "échec", None, sys.exc_info())
    PiiRedactingFilter().filter(record)
    assert "771234567" not in record.exc_text
