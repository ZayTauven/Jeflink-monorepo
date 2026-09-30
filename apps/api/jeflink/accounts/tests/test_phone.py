import pytest

from jeflink.accounts.phone import normalize_phone, phone_display, phone_region
from jeflink.accounts.validators import clean_display_name
from jeflink.common.errors import DomainError


@pytest.mark.parametrize(
    "saisie",
    [
        "77 123 45 67",
        "771234567",
        "77-123-45-67",
        "77.123.45.67",
        "00221771234567",
        "+221 77 123 45 67",
        "221771234567",
        " +221771234567 ",
    ],
)
def test_toutes_les_formes_donnent_le_meme_e164(saisie):
    assert normalize_phone(saisie) == "+221771234567"


def test_nouvelle_plage_mobile_senegalaise_acceptee():
    # Plage absente des métadonnées : acceptée quand même (T3).
    assert normalize_phone("79 123 45 67") == "+221791234567"


def test_numero_etranger_normalise():
    assert normalize_phone("+33 6 12 34 56 78") == "+33612345678"
    assert phone_region("+33612345678") == "FR"


def test_fixe_sur_refuse():
    with pytest.raises(DomainError) as exc:
        normalize_phone("+33 1 42 68 53 00")
    assert exc.value.code == "phone_not_mobile"


@pytest.mark.parametrize("saisie", ["", "abc", "12", "77 12", "+999123"])
def test_saisie_invalide(saisie):
    with pytest.raises(DomainError) as exc:
        normalize_phone(saisie)
    assert exc.value.code == "phone_invalid"
    assert saisie not in str(exc.value) or saisie == ""


def test_affichage():
    assert phone_display("+221771234567") == "77 123 45 67"
    assert phone_display("+33612345678") == "+33 6 12 34 56 78"
    assert phone_region("+221771234567") == "SN"


@pytest.mark.parametrize("nom", ["Awa Diop", "Ibou", "Fatou Ndiaye Sarr", "Moussa  Fall"])
def test_nom_valide(nom):
    assert clean_display_name(nom) == " ".join(nom.split())


@pytest.mark.parametrize(
    ("nom", "code"),
    [
        ("A", "display_name_length"),
        ("x" * 81, "display_name_length"),
        ("Awa‮Diop", "display_name_invalid"),
        ("Awa​Diop", "display_name_invalid"),
        ("Support Jeflink", "display_name_reserved"),
        ("admin", "display_name_reserved"),
        ("Voir www.exemple.com", "display_name_reserved"),
        ("jeflink-promo.sn", "display_name_reserved"),
    ],
)
def test_nom_refuse(nom, code):
    with pytest.raises(DomainError) as exc:
        clean_display_name(nom)
    assert exc.value.code == code
