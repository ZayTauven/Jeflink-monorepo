"""Encodage SMS : un seul caractère hors GSM-7 fait passer le SMS en UCS-2 (70 caractères).

Les gabarits OTP sont testés avec ``segments()`` pour tenir en un SMS facturé.
"""

import math

_BASIC = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
_EXTENDED = "^{}\\[~]|€\f"  # comptent pour 2 septets
BASIC_SET = frozenset(_BASIC)
EXTENDED_SET = frozenset(_EXTENDED)


def is_gsm7(text: str) -> bool:
    return all(ch in BASIC_SET or ch in EXTENDED_SET for ch in text)


def septets(text: str) -> int:
    return sum(2 if ch in EXTENDED_SET else 1 for ch in text)


def segments(text: str) -> int:
    """Nombre de SMS facturés pour ``text``."""
    if is_gsm7(text):
        size = septets(text)
        return 1 if size <= 160 else math.ceil(size / 153)
    # UCS-2 : les caractères hors BMP (emojis) comptent double.
    size = sum(2 if ord(ch) > 0xFFFF else 1 for ch in text)
    return 1 if size <= 70 else math.ceil(size / 67)
