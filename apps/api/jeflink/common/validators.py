"""Validation des textes saisis par l'Ops et publiés tels quels (spec 006)."""

import re

from django.core.exceptions import ValidationError

from .pii import contains_pii

_URL = re.compile(
    r"https?://|www\.|\b[a-z0-9-]+\.(?:com|net|org|info|biz|io|me|ly|co|app|sn|fr)\b",
    re.IGNORECASE,
)


def validate_public_text(value: str) -> None:
    """Refuse un numéro de téléphone (motifs de ``common.pii``) ou une URL.

    Le texte sera publié sur le site public : un numéro y serait lu par tout le monde, et un lien
    mènerait hors de Jeflink.
    """
    if contains_pii(value):
        raise ValidationError(
            "Un numéro de téléphone ne peut pas figurer ici.", code="contains_phone"
        )
    if _URL.search(value):
        raise ValidationError("Un lien ne peut pas figurer ici.", code="contains_url")
