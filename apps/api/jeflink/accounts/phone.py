"""Numéros de téléphone : identifiant principal, stocké en E.164 (règle 5, spec 001)."""

import re

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat, PhoneNumberType

from jeflink.common.errors import DomainError

_SEPARATORS = re.compile(r"[\s.\-()/]")
# Mobiles sénégalais : 7 + 8 chiffres. Acceptés même si les métadonnées libphonenumber
# ne connaissent pas encore la plage (nouvelles plages des opérateurs, T3).
_SN_MOBILE = re.compile(r"^\+2217\d{8}$")


def normalize_phone(raw: str, default_region: str = "SN") -> str:
    """Saisie libre → E.164. Lève ``phone_invalid`` ou ``phone_not_mobile`` (sans écho)."""
    cleaned = _SEPARATORS.sub("", raw or "")
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    elif cleaned.startswith("221") and len(cleaned) == 12:
        cleaned = "+" + cleaned
    try:
        number = phonenumbers.parse(cleaned, default_region)
    except NumberParseException as exc:
        raise DomainError("phone_invalid") from exc
    e164 = phonenumbers.format_number(number, PhoneNumberFormat.E164)
    if _SN_MOBILE.match(e164):
        return e164
    if not phonenumbers.is_valid_number(number):
        raise DomainError("phone_invalid")
    if phonenumbers.number_type(number) == PhoneNumberType.FIXED_LINE:
        raise DomainError("phone_not_mobile")
    return e164


def phone_region(e164: str) -> str:
    """Code région ISO (``SN``, ``FR``…) d'un numéro E.164 déjà normalisé."""
    if _SN_MOBILE.match(e164):
        return "SN"
    return phonenumbers.region_code_for_number(phonenumbers.parse(e164)) or ""


def phone_display(e164: str) -> str:
    """Format lisible : national pour le Sénégal (``77 123 45 67``), international sinon."""
    if _SN_MOBILE.match(e164):
        digits = e164[4:]
        return f"{digits[:2]} {digits[2:5]} {digits[5:7]} {digits[7:]}"
    number = phonenumbers.parse(e164)
    return phonenumbers.format_number(number, PhoneNumberFormat.INTERNATIONAL)
